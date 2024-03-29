import asyncio
import enum
import gc
import logging
import queue
import time
import traceback
from multiprocessing import Queue
from typing import List, Any, Tuple, Dict, Optional, Sequence, final

from ... import stronginfo
from .message import Message
from .telemetry import TelemetryInformation
from .variable import Variable, VariableType


class DeviceBackend:
    """This is a back-end thread for a device, which maintains the communication with the hardware, as well as notifies
    the front-end process whenever a state variable changes.

    The logics is based on several coroutines, each running its own infinite loop and handing over the control to the
    others when idle:
        - processFrontendMessages:
            frequently polls a multiprocessing Queue to see if the front-end needs the backend to do something
        - hardwareSender:
            sends messages to the hardware over a TCP/IP socket
        - hardwareReceiver:
            receives messages from the hardware through a TCP/IP socket
        - autoquerier:
            periodically schedules queries to the hardware for changes in the values of internal state variables
        - telemetry:
            periodically report the status of the back-end process to the front-end.

    For the synchronization, the following locks/envents/queues are present:

        - inqueue:
            multiprocessing.Queue: for receiving instructions from the front-end process
            - read by:
                processFrontendMessages
            - written by:
                front-end process
        - outqueue:
            multiprocessing.Queue for sending results/log/status etc. to the front-end process
            - read by:
                front-end process
            - written by:
                several methods of the back-end class
        - outbuffer:
            asyncio.Queue for storing hardware-bound messages to be sent over the TCP/IP socket
            - read by:
                hardwareSender
            - written by:
                several methods of the back-end class
        - stopevent:
            asyncio.Event to signal all coroutines to exit.
            - read by:
                telemetry, hardwareSender, hardwareReceiver, autoquerier, telemetry
            - written by:
                processFrontendMessages
        - autoqueryenabled:
            asyncio.Event to allow/inhibit automatic query when the hardware device is busy
            - read by:
                autoquerier
            - written by:
                several methods of the back-end class
        - cleartosend:
            asyncio.Event to signal if a new message can be sent to the hardware
            - read by:
                hardwareSender
            - written by:
                hardwareReceiver
        - remotedisconnected:
            asyncio.Event to signal if the remote end (hardware device) has disconnected.
            - read by:
                hardwareSender
            - written by:
                hardwareReceiver
    """

    class PanicState(enum.Enum):
        NoPanic = enum.auto()
        Panicking = enum.auto()
        Panicked = enum.auto()

    class Status:
        Idle = 'idle'
        Busy = 'busy'

    class CommandErrorMessage:
        pass

    class VariableInfo:
        name: str
        dependsfrom: List[str]
        urgent: bool
        timeout: float
        vartype: VariableType

        def __init__(self, name: str, dependsfrom: Optional[Sequence[str]] = None, urgent: bool = False,
                     timeout: float = 1.0, vartype: VariableType = VariableType.UNKNOWN):
            self.name = name
            self.dependsfrom = list(dependsfrom) if dependsfrom is not None else []
            self.urgent = urgent
            self.timeout = timeout
            self.vartype = vartype

    varinfo: List[VariableInfo]  # class-level variable: static information on state variables
    variables: List[Variable]  # instance-level information: volatile information on state variables
    inqueue: Queue  # we get messages from the front-end through this queue
    outqueue: Queue  # we send messages to the front-end through this queue
    inbuffer: bytes  # buffer of input data from the hardware
    outbuffer: asyncio.queues.Queue
    outbuffer_max: int = None  # maximum number of outgoing messages.
    streamreader: asyncio.StreamReader = None
    streamwriter: asyncio.StreamWriter = None
    asyncloop: asyncio.AbstractEventLoop = None
    asynctasks: Dict[str, asyncio.Task] = None
    stopevent: asyncio.Event = None
    cleartosend: asyncio.Event = None
    wakeautoquery: asyncio.Event = None
    remotedisconnected: asyncio.Event = None
    lastsendtime: float = None
    lastrecvtime: float = None
    messagereplytimeout: float = 1.0
    messageretries: int = 0
    messagemaxretries: int = 10
    outstandingqueryfailtimeout: float = 5.0
    delaybetweensends: float = 0.0

    lastmessage: Optional[Tuple[bytes, int]] = None
    telemetryPeriod: float = 5.0  # telemetry period in seconds
    telemetryInformation: Optional[TelemetryInformation] = None
    variablesready: bool = False
    autoqueryenabled: asyncio.Event = None

    # buffer for log messages before initialization
    logbuffer: Optional[List[Message]] = None
    panicking: PanicState = PanicState.NoPanic

    def __init__(self, inqueue: Queue, outqueue: Queue, host: str, port: int, **kwargs):
        self.inqueue = inqueue
        self.outqueue = outqueue
        self.variables = [Variable(vi.name, vi.timeout, vi.vartype) for vi in self.varinfo]
        assert '__status__' not in [v.name for v in self.variables]
        assert '__auxstatus__' not in [v.name for v in self.variables]
        self.variables.append(Variable('__status__', None, VariableType.STR))
        self.variables.append(Variable('__auxstatus__', None, VariableType.STR))
        self.inbuffer = b''
        self.host = host
        self.port = port
        self.asynctasks = {}
        self.logbuffer = []

    @classmethod
    def create_and_run(cls, inqueue: Queue, outqueue: Queue, host: str, port: int, **kwargs):
        """Create an instance and run the main thread. A convenience class method, useful for starting subprocesses."""
        obj = cls(inqueue, outqueue, host, port, **kwargs)
        asyncio.run(obj.main())

    #        obj.debug(f'Asyncio main thread ended.')

    ### Main process and its subtasks
    @final
    async def main(self):
        """This is the main loop of the backend. It has the following responsibilities:

            - maintain communication with the main process through two queues
            - periodically query changes in the hardware (send messages)
            - read and interpret messages from the hardware.
        """
        # first of all, send the list of variables to the front-end
        self.messageToFrontend('variablenames', names=[(v.name, v.defaulttimeout, v.vartype) for v in self.variables])
        for msg in self.logbuffer:
            self.outqueue.put_nowait(msg)
        self.logbuffer = None
        self.updateVariable('__status__', 'initializing')
        self.updateVariable('__auxstatus__', None)
        self.asyncloop = asyncio.get_running_loop()
        self.stopevent = asyncio.Event()
        self.cleartosend = asyncio.Event()
        self.cleartosend.set()
        self.remotedisconnected = asyncio.Event()
        self.outbuffer = asyncio.PriorityQueue(len(self.variables))
        self.autoqueryenabled = asyncio.Event()
        self.autoqueryenabled.set()
        self.wakeautoquery = asyncio.Event()
        try:
            self.streamreader, self.streamwriter = await asyncio.open_connection(self.host, self.port)
        except Exception as exc:
            self.error(f'Connection error to device: {repr(exc)}')
            self.messageToFrontend('end', expected=False)
            return
        # flush the incoming stream: remove residual data
        # Because streamreader.read() will block until something is to be read, we create a timeout task, and
        # run the two together.
        done, pending = await asyncio.wait(
            [asyncio.create_task(self.streamreader.read(), name='flush'),
             asyncio.create_task(asyncio.sleep(0.1), name='sleep')], return_when=asyncio.FIRST_COMPLETED)
        # at this point, at least one of the tasks is done. Either the reader or the timeout, or both (but the
        # probability of this is very small). We need to reap those
        for donetask in done:
            if donetask.get_name() == 'flush':
                self.debug(f'Flushed input queue: {len(donetask.result()):d} bytes.')
        # kill all pending tasks, if present.
        for task in pending:
            task.cancel()

        # Start the main loop by creating several concurrently running tasks
        name2coro = {'processFrontendMessages': self.processFrontendMessages,
                     'hardwareSender': self.hardwareSender,
                     'hardwareReceiver': self.hardwareReceiver,
                     'autoquerier': self.autoquerier,
                     'telemetry': self.telemetry}
        pending = {asyncio.create_task(value(), name=key) for key, value in name2coro.items()}
        try:
            try:
                while True:
                    # this is the main loop. Submit all tasks and wait until the first one is completed.
                    done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    # check all tasks which have ended, reap them and restart them.
                    for donetask in done:
                        # collect some statistics on this task in the telemetry.
                        if self.telemetryInformation is not None:
                            if donetask.get_name() not in self.telemetryInformation.coro_wakes:
                                self.telemetryInformation.coro_wakes[donetask.get_name()] = 0
                            self.telemetryInformation.coro_wakes[donetask.get_name()] += 1
                        # if we are not stopping, re-schedule the finished task
                        if (not self.stopevent.is_set()) and (donetask.result()):
                            # each task returns True if it wants to be re-scheduled and False if not.
                            pending.add(asyncio.create_task(name2coro[donetask.get_name()](), name=donetask.get_name()))
                        # check if we have an exception.
                        exc = donetask.exception()
                        if exc:
                            # an exception has occurred. Handle the exception and then kill all pending tasks.
                            try:
                                raise exc
                            except Exception as exc:
                                self.error(f'Exception occurred in the back-end thread: {traceback.format_exc()}')
                                for task in pending:
                                    task.cancel()
                                pending = []
                                break
                    # when there are no more running coroutines (either because none wanted to be rescheduled, or one has
                    # thrown an exception, or the `stopevent` is set, exit from the main loop
                    if not pending:
                        break
                # after the main loop has ended, we disconnect from the hardware.
            finally:
                # ensure that we always disconnect from the hardware, even in the case of an unhandled exception in the
                # main loop
                await self.disconnectFromHardware()
        except Exception as exc:
            self.error(f'Exception occurred in the back-end thread: {repr(exc)}\n{traceback.format_exc()}')
        finally:
            # always notify the frontend that we exit.
            self.messageToFrontend('end', expected=self.stopevent.is_set())

    @final
    async def ensureready(self) -> bool:
        """Task to ensure that the device is ready, i.e. all variables have been successfully queried at least once."""
        await asyncio.sleep(self.readytimeout)
        if self.variablesready:
            return self.variablesready

    @final
    async def telemetry(self) -> bool:
        """Collect telemetry information periodically"""
        #        self.debug('Telemetry task started.')
        # `communicating` is True if a message has been sent to the device and we are waiting for a response.
        communicating = False
        if self.telemetryInformation is not None:
            # if we already have a telemetry information instance, finish data collection and send it to the frontend
            self.telemetryInformation.finish()
            self.telemetryInformation.outbufferlength = self.outbuffer.qsize()
            self.telemetryInformation.outstandingvariables = [v.name for v in self.variables if
                                                              not v.hasValidValue()]
            self.telemetryInformation.oldestbufferedmessageage = None
            now = time.monotonic()
            self.telemetryInformation.outdatedqueries = {
                v.name: (now - v.lastquery) for v in self.variables if
                (v.lastquery is not None) and (now - v.lastquery) > self.telemetryPeriod}
            self.telemetryInformation.autoqueryinhibited = not self.autoqueryenabled.is_set()
            self.telemetryInformation.cleartosend = self.cleartosend.is_set()
            self.telemetryInformation.socket_eof = self.streamreader.at_eof()
            self.telemetryInformation.lastmessage = self.lastmessage
            self.telemetryInformation.lastsendtime = self.lastsendtime
            self.telemetryInformation.lastrecvtime = self.lastrecvtime
            self.telemetryInformation.asyncio_tasks = [t.get_name() for t in asyncio.all_tasks()]
            self.messageToFrontend('telemetry', telemetry=self.telemetryInformation)
            # check if we have successfully queried all variables in the given time.
            for timeout in self.telemetryInformation.outdatedqueries.values():
                if (timeout > self.outstandingqueryfailtimeout) and (self.autoqueryenabled.is_set()):
                    raise RuntimeError(f'Outstanding query fail timeout reached. Variables not yet queried: '
                                       f'{", ".join(sorted(self.telemetryInformation.outdatedqueries))}')
            communicating = self.telemetryInformation.communicating
            # start with a new telemetry information instance.
            del self.telemetryInformation
            self.telemetryInformation = None
        gc.collect()
        self.telemetryInformation = TelemetryInformation(communicating)
        t0 = time.monotonic()
        # start an interruptible wait for `self.telemetryPeriod` seconds. It can be ended earlier if `self.stopevent`
        # is set
        telemetrytask = asyncio.create_task(asyncio.sleep(self.telemetryPeriod if self.variablesready else 0.5),
                                            name='tm_task')
        stoptask = asyncio.create_task(self.stopevent.wait(), name='tm_stoptask')
        done, pending = await asyncio.wait({telemetrytask, stoptask}, return_when=asyncio.FIRST_COMPLETED)
        #        self.debug(f'Telemetry task slept {time.monotonic() - t0} seconds.')
        # reap all remaining coroutines
        for t in pending.union(done):
            t.cancel()
        if stoptask in done:
            # stop was requested, exit cleanly and notify the main loop that we don't want to be rescheduled
            return False
        # otherwise we want to be rescheduled.
        return True

    @final
    async def processFrontendMessages(self) -> bool:
        """Process a message from the front-end"""
        while True:
            try:
                message = self.inqueue.get_nowait()
                # self.inqueue.task_done()
            except queue.Empty:
                # this is ugly, but multiprocessing Queues cannot be awaited.
                await asyncio.sleep(0.1)
                return True
            else:
                assert isinstance(message, Message)
                if message.command == 'issuecommand':
                    if self.panicking != self.PanicState.NoPanic:
                        self.commandError(message.kwargs['name'], 'Cannot issue command due to panic state.')
                    else:
                        self.issueCommand(name=message.kwargs['name'], args=message.kwargs['args'])
                elif message.command == 'end':
                    self.stopevent.set()
                    return False
                elif message.command == 'panic':
                    self.panicking = self.PanicState.Panicking
                    self.doPanic()
                    return True

    @final
    async def hardwareSender(self) -> bool:
        """Try to send outstanding messages to the hardware.

        This method should not be overridden in subclasses.
        """
        # this coroutine must sleep until at least one of the following happens:
        # 1) the remote side disconnected
        # 2) there is something to send AND we can send, i.e. not waiting for a reply from the hardware.
        # 3) the reply timeout is elapsed: we need to re-send the message
        # 4) stop is requested by the front-end

        # Check if the remote end has disconnected. We get the notification from hardwareReceiver.
        remotedisconnectedtask = asyncio.create_task(self.remotedisconnected.wait(), name='hws_remotedisconnectedtask')

        # check if the reply timeout has elapsed after the last send and we did not get a reply.
        if (self.lastsendtime is not None) and (self.lastrecvtime is not None) and (
                self.lastsendtime > self.lastrecvtime):
            delay = (self.messagereplytimeout - (time.monotonic() - self.lastsendtime))
            #            self.debug(f'Reply timeout delay: {delay}')
            replytimeouttask = asyncio.create_task(asyncio.sleep(delay), name='hws_replytimeouttask')
        else:
            #            self.debug('Not creating a reply timeout task.')
            replytimeouttask = None

        # check if the front-end wants us to cease operation
        stoptask = asyncio.create_task(self.stopevent.wait(), name='hws_stopevent')

        # Check if we have something to send.
        async def wait_outbuffer():
            try:
                #                self.warning('Waiting for outbuffer')
                t0 = time.monotonic()
                result = await self.outbuffer.get()
                #                self.debug(f'Got result from outbuffer after {time.monotonic() - t0} seconds: {result}')
                #                self.info(f'Outbuffer length is now: {self.outbuffer.qsize()}')
                self.outbuffer.task_done()
                return result
            except asyncio.exceptions.CancelledError:
                #                self.warning(f'Wait for outbuffer cancelled after {time.monotonic() - t0} seconds.')
                raise

        outbuffertask = asyncio.create_task(wait_outbuffer(), name='hws_outbuffer')

        # check if we are able to send, i.e. we got the reply for our previous request.
        cleartosendtask = asyncio.create_task(self.cleartosend.wait(), name='hws_cleartosend')

        # combine the last two tasks into one and check them together. We may only send a message to the hardware if
        # we got the reply AND we have something to send.

        cansendtask = asyncio.create_task(
            asyncio.wait({outbuffertask, cleartosendtask}, return_when=asyncio.ALL_COMPLETED), name='hws_cansend')
        tasks = {cansendtask, remotedisconnectedtask, stoptask}.union(
            {replytimeouttask} if replytimeouttask is not None else set())
        #        self.debug(f'Sender going to sleep with tasks {[t.get_name() for t in tasks]}')
        #        self.debug(f'Outbuffer length before sleep: {self.outbuffer.qsize()}')
        t0 = time.monotonic()
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED)
        for t in [cansendtask, remotedisconnectedtask, stoptask, outbuffertask, cleartosendtask] + (
        [replytimeouttask] if replytimeouttask is not None else []):
            if not t.done():
                t.cancel()
        if (remotedisconnectedtask in done) or (stoptask in done):
            # either it is our time to disconnect or the other side won't send anything more to us
            return False
        elif cansendtask in done:
            priority, (message, nreplies, puttime) = outbuffertask.result()
            await self._dosend(message, nreplies)
        elif (replytimeouttask is not None) and (replytimeouttask.done()):
            try:
                priority, (message, nreplies, puttime) = outbuffertask.result()
            except asyncio.exceptions.InvalidStateError:
                pass
            else:
                # if we have a message in the output buffer, put it back
                #                self.warning(f'Putting back {message}')
                self.outbuffer.put_nowait((priority, (message, nreplies, puttime)))
            if (self.lastsendtime is None) or (self.lastrecvtime > self.lastsendtime):
                #                self.debug('False alarm in replytimeouttask')
                return True
            #            self.warning(f'Reply timeout #{self.messageretries+1} / {self.messagemaxretries}')
            if self.messageretries >= self.messagemaxretries:
                raise RuntimeError('Reached maximal number of send retries')
            self.messageretries += 1
            if self.messageretries > 1:
                # only issue a warning on the 2nd retry
                self.warning(
                    f'Reply timeout, retrying sending of message {self.lastmessage[0]=}, {self.lastmessage[1]=}')
            await self._dosend(self.lastmessage[0], self.lastmessage[1])
        #        self.debug('Sender done.')
        return True

    @final
    async def _dosend(self, message: bytes, nreplies: int):
        if (self.lastsendtime is not None) and (self.delaybetweensends > 0):
            # ensure a delay between two sends
            time.sleep(max(time.monotonic() - self.lastsendtime - self.delaybetweensends, 0))
        self.streamwriter.write(message)
        self.lastsendtime = time.monotonic()
        if self.telemetryInformation is not None:
            self.telemetryInformation.setCommunicating(True)
            self.telemetryInformation.bytessent += len(message)
            self.telemetryInformation.messagessent += 1
        self.lastmessage = message, nreplies
        self.cleartosend.clear()
        await self.streamwriter.drain()

    #        self.debug(f'Message {message} sent')

    @final
    async def hardwareReceiver(self) -> bool:
        """Receive messages from the hardware.

        This method should not be overridden in subclasses.
        """
        #        self.debug('Receiver running.')
        readtask = asyncio.create_task(self.streamreader.read(1024), name='hwrecv_readtask')
        stoptask = asyncio.create_task(self.stopevent.wait(), name='hwrecv_stoptask')
        done, pending = await asyncio.wait({readtask, stoptask}, return_when=asyncio.FIRST_COMPLETED)
        #        self.debug('Receiver awoke.')
        for task in pending.union(done):
            task.cancel()
        if stoptask in done:
            # Don't receive anything anymore.
            # Disconnecting from the hardware is the task of the writer.
            return False
        if readtask in done:
            recv = readtask.result()
            self.lastrecvtime = time.monotonic()
            self.messageretries = 0
            self.inbuffer += recv
            messages, remaining = self._cutmessages(self.inbuffer)
            if self.telemetryInformation is not None:
                self.telemetryInformation.setCommunicating(False)
                self.telemetryInformation.bytesreceived += len(recv)
                self.telemetryInformation.messagesreceived += len(messages)
            self.inbuffer = remaining
            for msg in messages:
                if (not self.lastmessage) or (self.lastmessage is None):
                    self.error(f'Message received ({msg}) without a query.')
                    raise RuntimeError(f'Message received ({msg}) without a query.')
                self.interpretMessage(msg, self.lastmessage[0])
            if self.lastmessage is not None:
                self.lastmessage = self.lastmessage[0], self.lastmessage[-1] - len(messages)
            if (self.lastmessage is None) or (self.lastmessage[1] <= 0):
                self.lastmessage = None
                self.cleartosend.set()
            if self.streamreader.at_eof():
                # the other end won't send us anything. Neither would we. Actual disconnection is the task of the
                # writer coroutine.
                self.remotedisconnected.set()  # this will notify the writer coroutine
                return False
        #        self.debug('Receiver done.')
        return True

    @final
    async def autoquerier(self) -> bool:
        """see which variables need updating and issue queries for them"""
        stoptask = asyncio.create_task(self.stopevent.wait(), name='aq_stoptask')  # check for stop
        lowest_timeout = min([v.querytimeout for v in self.variables if (v.querytimeout is not None)])
        now = time.monotonic()
        overdue_variables = [(v.name, v.overdue(now)) for v in self.variables if
                             (v.overdue(now) > 0) and (v.lastquery is None)]
        if overdue_variables:
            lowest_timeout = 0.1
        waittask = asyncio.create_task(asyncio.sleep(lowest_timeout), name='aq_waittask')
        locktask = asyncio.create_task(self.autoqueryenabled.wait(), name='aq_locktask')
        #        if hasattr(self, 'motionstatus') and self.motionstatus:
        #            self.debug('Autoquery will sleep for {} seconds'.format(lowest_timeout))
        #            self.debug(f'Autoquery enabled: {self.autoqueryenabled.is_set()}')
        self.wakeautoquery.clear()
        waketask = asyncio.create_task(self.wakeautoquery.wait(), name='aq_waketask')
        wakeorwaittask = asyncio.create_task(asyncio.wait({waittask, waketask}, return_when=asyncio.FIRST_COMPLETED),
                                             name='aq_wakeorwaittask')
        canquerytask = asyncio.create_task(asyncio.wait({wakeorwaittask, locktask}, return_when=asyncio.ALL_COMPLETED),
                                           name='aq_canquerytask')

        # Now commence waiting. The autoquery coroutine will wake up when EITHER the stop event is set OR the canquery
        # task finishes.
        done, pending = await asyncio.wait({stoptask, canquerytask}, return_when=asyncio.FIRST_COMPLETED)
        for task in {waittask, locktask, waketask, wakeorwaittask, canquerytask, stoptask}:
            task.cancel()
        #        self.wakeautoquery.clear()
        if stoptask in done:
            return False
        elif (canquerytask in done) and (self.autoqueryenabled.is_set()):
            # we need to check the autoquery enabled event explicitely: it may have been cleared while waiting for the
            # time of the next query
            now = time.monotonic()
            # Query the variables smartly. First of all, only query variables which:
            #   - can be queried
            #   - do not have any outstanding (i.e. unreplied) queries
            #   - are not dependent from others.
            #   - are overdue, i.e. the last result is older than the query period
            #                if hasattr(self, 'motionstatus') and self.motionstatus:
            #                    var = self.getVariable('actualposition$1')
            #                    vi = [vi for vi in self.varinfo if vi.name == var.name][0]
            #                    self.debug(str(var))
            #                    self.debug(str(vi.dependsfrom))
            assert all([v.name == vi.name for v, vi in zip(self.variables, self.varinfo)])
            queryable = [(v, vi) for v, vi in zip(self.variables, self.varinfo)
                         if v.queriable() and
                         (v.lastquery is None) and
                         # (not vi.dependsfrom) and  # do not check this!
                         (v.overdue(now) > 0)]
            overdue = [(v, vi) for v, vi in zip(self.variables, self.varinfo) if v.overdue(now) > 0]
            # if overdue:
            #    self.debug(f'Overdue variables (with lastquery times): {[(v.name, v.lastquery) for v, vi in overdue]}')
            # Now sort the remaining variables:
            #   - first according to their urgency
            #   - second according to their overdue-ness.
            sortedqueriable = sorted(queryable, key=lambda v_vi: (not v_vi[1].urgent, -v_vi[0].overdue(now)))
            #                self.debug(f'Queriable: {[v.name for v, vi in sortedqueriable]}')
            #           if hasattr(self, 'motionstatus') and self.motionstatus:
            #               self.debug(f'Sortedqueriable: {[v.name for v, vi in sortedqueriable]}')
            queried = []
            for variable, varinfo in sortedqueriable:
                if self.outbuffer.full():
                    # output buffer overflow, skip queries
                    self.warning(f'Skipping query: full output buffer')
                    break
                #                    self.debug(f'Querying variable {variable.name}')
                varnames = varinfo.dependsfrom if varinfo.dependsfrom else [variable.name]
                for name in varnames:
                    if name not in queried:
                        self.queryVariable(name)
                        queried.append(name)
            del queryable, sortedqueriable
        else:
            self.debug(f'Autoquery enabled: {self.autoqueryenabled.is_set()}')

        return True

    @final
    async def disconnectFromHardware(self):
        """Disconnect from the hardware"""
        self.streamwriter.close()
        try:
            await self.streamwriter.wait_closed()
        except ConnectionResetError:
            self.warning('Remote disconnected while waiting for closed.')

    ### Tools for subclasses to use
    @final
    def disableAutoQuery(self):
        # self.debug('Disabling autoquery')
        self.autoqueryenabled.clear()
        for v in self.variables:
            v.lastquery = None

    @final
    def enableAutoQuery(self):
        # self.debug('Enabling autoquery')
        for v in self.variables:
            v.lastquery = None
        self.autoqueryenabled.set()

    @final
    def commandFinished(self, commandname: str, result: str):
        self.messageToFrontend('commandfinished', commandname=commandname, result=result)

    @final
    def commandError(self, commandname: str, errormessage: str):
        self.messageToFrontend('commanderror', commandname=commandname, errormessage=errormessage)

    @final
    def messageToFrontend(self, message, **kwargs):
        """Send a message to the front-end."""
        self.outqueue.put(Message(message, **kwargs))

    @final
    def queryVariable(self, name: str, force: bool = False):
        """Schedule a query for a variable.

        Only schedules if there are no outstanding queries yet.

        Always schedules, even if the outgoing messages buffer is full.
        """
        var, varinfo = [(v, vi) for v, vi in zip(self.variables, self.varinfo) if v.name == name][0]
        if force:
            var.lastchange = None
        variablestoquery = [self.getVariable(vname) for vname in varinfo.dependsfrom] if varinfo.dependsfrom else [
            var]
        for var in set(variablestoquery):
            if var.lastquery is not None:
                # this variable has already been queried and no reply received yet, don't schedule another query.
                var.lastquery = time.monotonic()
                return
            var.lastquery = time.monotonic()
            self._query(var.name)

    @final
    def enqueueHardwareMessage(self, message: bytes, numreplies: int = 1, urgencymodifier: float = 0.0):
        """Put a new message to the outbound queue to the hardware.

        This method should not be overridden in subclasses.
        """
        self.outbuffer.put_nowait((time.monotonic(), (message, numreplies, time.monotonic() - urgencymodifier)))

    #        self.debug(f'Enqueued message {message}, num replies {numreplies}')
    #        self.debug(f'Output buffer length after enqueueing message: {self.outbuffer.qsize()}')
    @final
    def updateVariable(self, varname: str, newvalue: Any) -> bool:
        """Update the value of a variable.

        :param varname: name of the variable
        :type varname: str
        :param newvalue: new value of the variable
        :type newvalue: any
        :return: True if the new value is different from the previous one, False if they are the same.
        :rtype: bool
        """
        variable = self.getVariable(varname)
        if (self.telemetryInformation is not None) and (variable.lastquery is not None):
            self.telemetryInformation.querytimes.append(time.monotonic() - variable.lastquery)
        try:
            if variable.update(newvalue):
                self.messageToFrontend('variableChanged', name=variable.name, value=variable.value,
                                       previousvalue=variable.previousvalue)
                try:
                    self.onVariableChanged(variable.name, variable.value, variable.previousvalue)
                except Exception as exc:
                    self.error(
                        f'Exception in backend onVariableChanged callback on variable {variable.name}, '
                        f'new value {variable.value}')
                return True
            else:
                return False
        finally:
            if self.checkIfJustBecameReady():
                self.variablesready = True
                self.log(logging.STRONGINFO, f'All variables ready.')
                self.messageToFrontend('ready')
                if self['__status__'] is None:
                    # only update the '__status__' variable if it has not yet been initialized by some query.
                    self.updateVariable('__status__', 'idle')
                self.onVariablesReady()

    def checkIfJustBecameReady(self) -> bool:
        """Check if the device just became ready"""
        return (not self.variablesready) and all([v.timestamp is not None for v in self.variables])

    @final
    def getVariable(self, varname: str) -> Variable:
        """Get the `Variable` instance corresponding to a name

        :param varname: variable name
        :type varname: str
        :return: the corresponding variable
        :rtype: Variable
        :raises KeyError: if not found
        """
        try:
            return [v for v in self.variables if v.name == varname][0]
        except IndexError:
            raise KeyError(f'Variable {varname} does not exist')

    @final
    def __getitem__(self, item: str) -> Any:
        """Get the value of a variable

        :param item: variable name
        :type item: str
        :return: the current value of the variable
        :rtype: any
        :raises KeyError: if not found or if the variable has not yet been queried.
        """
        try:
            return [v.value for v in self.variables if v.name == item and v.hasValidValue()][0]
        except IndexError:
            raise KeyError(item)

    ### Logging
    @final
    def log(self, level: int, message: str):
        if self.logbuffer is None:
            self.messageToFrontend('log', level=level, logmessage=message)
        else:
            self.logbuffer.append(Message('log', level=level, logmessage=message))

    @final
    def debug(self, message: str):
        return self.log(logging.DEBUG, message)

    @final
    def warning(self, message: str):
        return self.log(logging.WARNING, message)

    @final
    def error(self, message: str):
        return self.log(logging.ERROR, message)

    @final
    def info(self, message: str):
        return self.log(logging.INFO, message)

    ### ABSTRACT METHODS FOR HIGHER LEVEL COMMUNICATION REQUIRING INTERPRETATION OF THE MESSAGES

    def _query(self, variablename: str):
        """Issue a message to the hardware to query a variable.

        This method must construct the message to the hardware. It must not send it directly, instead should call
        enqueueHardwareMessage() with the message.
        """
        raise NotImplementedError

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        """Cut a long message into distinct messages

        :param message: a long string of bytes, possibly containing multiple messages
        :type message: bytes
        :return: a (possibly empty) list of distinct messages and the remaining bytes of the last, incomplete message
            (possibly an empty byte string if only complete messages are read).
        :rtype: tuple of a list of bytes and a bytes instance.
        """
        raise NotImplementedError

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        """Interpret a message from the hardware.

        This method should do one of the following:
            - call updateVariable()
            - send a warning/error message using the respective methods

        """
        raise NotImplementedError

    def issueCommand(self, name: str, args: Sequence[Any]):
        raise NotImplementedError

    def onVariablesReady(self):
        pass

    def doPanic(self):
        """Perform actions when a panic situation occurs.

        The default implementation simply sends an acknowledgement reply to the front-end.
        """
        self.panicking = self.PanicState.Panicked
        self.messageToFrontend('panicacknowledged')

    def panic(self, reason: str):
        """Notify the front-end thread of a panic situation."""
        self.messageToFrontend('panic', reason=reason)

    def onVariableChanged(self, name: str, newvalue: Any, oldvalue: Any):
        pass
