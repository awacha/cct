import logging
import multiprocessing
import queue
import time
import traceback
from logging.handlers import QueueHandler
from typing import Dict, List, Optional, Tuple

from .exceptions import CommunicationError, DeviceError, InvalidMessage, WatchdogTimeout
from .message import Message
from ...utils.telemetry import TelemetryInfo


class QueueLogHandler(QueueHandler):
    def prepare(self, record):
        return Message('log', 0, 'logger', logrecord=record)


class ExitWorkerLoop(Exception):
    pass

class Watchdog(object):
    """A simple timeout-keeper watchdog.
    """

    def __init__(self, timeout: Optional[float]):
        """Initialize the watchdog. The watchdog is initialized enabled by default.

        :param timeout: the timeout in seconds
        """
        if timeout <= 0:
            raise ValueError('Timeout must be positive')
        self.timeout = timeout
        self.active = True
        self.timestamp = time.monotonic()

    def disable(self):
        """Disable the watchdog"""
        self.active = False

    def enable(self):
        """Enable the watchdog"""
        self.active = True

    def check(self, raise_exception=True) -> bool:
        """Check if the elapsed time is larger than the timeout.

        :param raise_exception: if WatchdogTimeout exception is to be raised
            when the watchdog times out
        :type raise_exception: bool

        :return: True if not yet timed out. False if timed out and raise_exception is False
        :rtype: bool

        :raise: WatchdogTimeout exception if times out and raise_exception is True.
        """
        if self.timeout is None:
            return True
        if self.active and (self.elapsed() > self.timeout):
            if raise_exception:
                raise WatchdogTimeout
            else:
                return False
        return True

    def pat(self):
        """Pat the watchdog: reset the timestamp"""
        self.timestamp = time.monotonic()

    def elapsed(self) -> float:
        """The elapsed time in seconds since the last pat"""
        return time.monotonic() - self.timestamp


class DeviceBackend(object):
    """This class implements a backend process for the devices of cct.

    This class is responsible to maintain continuous communication with the hardware, frequently polling it for changes
    in its state variables. Whenever a state variable changes, it notifies the frontend process of the new value through
    a queue.

    Other processes (mostly the front-end) can request communication with the device using two mechanisms:

    'set variable': set a state variable
    'execute command': execute a command on the device.

    Both these happen with messages passed through `inqueue`. The replies are sent through `outqueue`.

    Note that reusing instances of this class is not recommended: every time the device is (re)connected, another
    instance of this class has to be made for the purpose.

    Messages through the `inqueue` are dicts with the following required fields:

    'type': the message type (string), see below
    'source': the name of the process/thread who sent the message
    'id': a unique identifier
    'timestamp': time of the message (generated with time.monotonic())

    The following 'type's are known:

    'config': the frontend sends the updated configuration dictionary in the 'configdict' key.
    'exit': the frontend requests the backend to disconnect from the device and finish its work.
    'query': a state variable is to be re-queried from the device. 'name' is the variable name. If 'signal_needed'
        is True, the frontend expects to be notified on successful read of the variable, even if its value has not
        changed.
    'set': the value of the state variable variable 'name' has to be set to 'value'. The frontend does not get notified
        explicitely.
    'execute': a command 'name' is to be executed with the arguments 'arguments' (tuple)
    'communication_error': in some cases, when a different process is responsible for the actual communication, it can
        send this message to notify the backend thread of some fatal error, which results in the breakdown of connection
        with the device. Other fields are 'exception', which is the exception instance, and 'traceback', which is the
        traceback formatted with traceback.format_exc().
    'incoming': the communication process notifies the backend process of an incoming message from the device. The
        message is in the field 'message', and the originally sent message, to which this is a reply, is found in 'sent'
    'log': a formatted logrecord is in 'logrecord', which is passed to the frontend in a similar message.
    'send_complete': the communication subprocess notifies the backend that the message has been sent.

    In `outqueue`, this class can send the following messages (required fields are the same as above):

    'error': some error happened. Fields: 'variablename': if the error can be related to a state variable, then its
        name. Otherwise None. 'exception': the exception instance. 'traceback': the traceback as a string, formatted
        with traceback.format_exc()
    'exited': this is the last message to be sent through the queue. 'normaltermination': True if normal exit, False
        if due to some fatal error.
    'ready': the device became ready by reading all the state variables at least once.
    'telemetry': 'data' carries a telemetry dictionary
    'update': a state variable has changed. 'name' is the variable name, 'value' is its value.
    """

    # All timestamps are generated with time.monotonic()

    def __init__(self, name: str, configdir: str, config: Dict, deviceconnectionparameters: Tuple,
                 inqueue: multiprocessing.Queue, outqueue: multiprocessing.Queue,
                 watchdog_timeout: float, inqueue_timeout: float, query_timeout: float,
                 telemetry_interval: float, queryall_interval: float, all_variables: List[str],
                 minimum_query_variables: List[str], constant_variables: Optional[List[str]],
                 urgent_variables: Optional[List[str]], urgency_modulo: int, startup_number: int,
                 loglevel: int, logfile: str, log_formatstr: str, max_busy_level: int,
                 busysemaphore: multiprocessing.BoundedSemaphore):
        """Initialize the backend process

        :param name: the name of the device. Appears in log/error messages, therefore should be unique
        :param config: the initial configuration dictionary. Can be updated through the queue
        :param configdir: the path where the configuration files are to be stored
        :param deviceconnectionparameters: a tuple of the connection parameters (host, port, timeouts etc.). Used
            in subclasses.
        :param inqueue: The input queue for this backend process. See the class-level docstring for valid message types.
        :param outqueue: The output queue of this backend process. See the class-level docstring for details.
        :param watchdog_timeout: The watchdog timeout in seconds. If more than this time is elapsed after the last
            message received from the device, the device is considered irresponsive and disconnected.
        :param inqueue_timeout: Timeout for waiting on the inqueue.
        :param query_timeout: After this time a query sent to the device is considered "lost".
        :param telemetry_interval: Minimum time between two telemetry gatherings.
        :param queryall_interval: Minimum time between automatic queries of _all_ device variables.
        :param all_variables: A list of all device variables
        :param minimum_query_variables: A minimum set of device variables. Querying all of these ensures reading all the
            state variables. Must include ALL variables needed for a fully defined state, including constant variables.
        :param constant_variables: A list of constant variables: these are queried only once, at the beginning.
        :param urgent_variables: Variables that need to be updated more frequently than the others. If None, all
            variables are considered urgent.
        :param urgency_modulo: Auto-queries only query the urgent variables in `urgent_variables`. All the others are
            queried only every `urgency_modulo`-eth "queryall". If zero, only urgent variables are queried, every time.
        :param startup_number: The number of this startup
        :param loglevel: Log level, as in the logger module.
        :param logfile: Log file name. Should be able to be open(<>, 'a', encoding='utf-8')-ed.
        :param log_formatstr: Format string for creating the log line. It is used as
            log_formatstr.format(**self.properties)
        :param max_busy_level: How many times the busy semaphore can be acquired
        :param busysemaphore: A semaphore which is acquired (typically from the frontend process) when a special
            operation is initiated, and released (typically by the backend) when the operation finishes.
        """
        self.name = name  # name of the device
        self.startup_number = startup_number
        self.logger = logging.getLogger(
            __name__ + '::' + self.name + '__backgroundprocess')
        self.logger.propagate = False
        if not self.logger.hasHandlers():
            self.logger.addHandler(QueueLogHandler(outqueue))
            self.logger.addHandler(logging.StreamHandler())
        self.logger.setLevel(loglevel)
        self.logger.debug(
            'Background thread started for {}, this is startup #{:d}. Log level: {:d} (effective: {:d})'.format(
                self.name, self.startup_number, self.logger.level, self.logger.getEffectiveLevel()))
        self.deviceconnectionparameters = deviceconnectionparameters
        self.config = config  # a copy of the configuration dictionary
        self.configdir = configdir
        self.inqueue = inqueue  # input queue
        self.outqueue = outqueue  # output queue
        self.inqueue_timeout = inqueue_timeout  # timeout for waiting for a message in the inqueue
        self.queryall_interval = queryall_interval
        self.query_timeout = query_timeout
        self.minimum_query_variables = minimum_query_variables
        self.constant_variables = constant_variables
        if self.constant_variables is None:
            self.constant_variables = []
        self.urgent_variables = urgent_variables
        self.urgency_modulo = urgency_modulo
        self.properties = {}  # dictionary holding the state variables of the instrument
        self.timestamps = {}  # timestamps for each state variable, holding the time of the last successful read.
        self.query_requested = {}  # the timestamps for each variable, holding the time of the last query.
        self.refresh_requested = {}  # counting the number of refresh requests for each variable.
        self.all_variables = all_variables  # list of the names of all variables.
        self.watchdog = Watchdog(watchdog_timeout)
        self.ready = False  # becomes True if all the state variables have been successfully read at least once.
        self.telemetry_interval = telemetry_interval  # the interval (seconds) to generate and send telemetry data
        self.lasttimes = {'telemetry': 0,
                          'queryall': 0,
                          'query': 0,
                          'send': 0,
                          'recv': 0,
                          }
        self.counters = {'queries': 0,
                         'queryalls': 0,
                         'inmessages': 0,
                         'outmessages': 0,
                         'outqueued': 0,
                         'inqueued': 0,
                         }
        self.busysemaphore = busysemaphore
        self.max_busy_level = max_busy_level
        self.logfile = logfile
        self.log_formatstr = log_formatstr
        self.logger.debug('Initialized background thread for {} successfully.'.format(self.name))

    def is_busy(self) -> int:
        """Returns how many times the busy semaphore has been acquired. This
        way, the return value casted to bool makes sense semantically."""
        return self.max_busy_level - self.busysemaphore.get_value()

    def send_to_frontend(self, msgtype: str, **kwargs):
        """
        Send a message to the frontend process.

        msgtype: the type of the message

        The common required fields (id, timestamp) are computed automatically.
        Give all the other required fields as keyword arguments.
        """
        self.counters['outqueued'] += 1
        msg = Message(msgtype, self.counters['outqueued'], self.name + '__backend', **kwargs)
        self.outqueue.put(msg)
        del msg

    def has_all_variables(self) -> bool:
        """Checks if all the variables have been requested and received at least once,
        by comparing the keys in self.properties to those in self.all_variables."""
        return not bool(self.get_missing_variables())

    def get_missing_variables(self):
        return [v for v in self.all_variables if v not in self.properties]

    def worker(self):
        """Worker function of the background thread. The main job of this is
        to run periodic checks on the hardware (polling) and updating
        `self.properties` accordingly, as well as writing log files.

        The communication between the front-end and back-end is only through
        `self.inqueue` and `self.outqueue`. See the details in the class-level
        docstring.

        This method should not be overloaded. The actual work is delegated to
        `set_variable()`, `execute_command()`, `interpret_message() and
        `query_variable()`: these should be overridden in subclasses.

        In some cases a separate process/thread is responsible for communication
        with the device. Upon an incoming message, that process should also
        use `self.inqueue` to send the message to this backend process. The
        worker method will then call `self.process_incoming_message` every time a
        new message comes. The latter is responsible to call `self.update_variable`.
        """
        message = None
        self.logger.debug('Starting worker method for device {}'.format(self.name))
        try:
            self.connect_device()
            assert (self.get_connected())
        except Exception as exc:
            self.disconnect_device(because_of_failure=True)
            self.send_to_frontend('error', variablename=None, exception=exc, traceback=traceback.format_exc())
            self.send_to_frontend('exited', normaltermination=False)
            return
        self.logger.debug('Connected to device successfully.')
        self.update_variable('_status', 'Initializing')
        self.update_variable('_auxstatus', None)
        exit_status = False  # abnormal termination
        while True:
            try:
                message = None
                try:
                    message = self.inqueue.get(
                        block=True, timeout=self.inqueue_timeout)
                    self.counters['inqueued'] += 1
                    assert isinstance(message, Message)
                except queue.Empty:
                    pass
                else:
                    # if no message was pending, a queue.Empty exception has
                    # already been raised at this point.
                    try:
                        exit_status = self.dispatch_inqueue_message(message)
                    except ExitWorkerLoop as ewl:
                        exit_status = ewl.args[0]
                        break
                # Do some housekeeping
                # 1) check if we have just became ready, i.e. we have read all variables at least once. If yes,
                #     notify the frontend thread.
                if (not self.ready) and (self.has_all_variables()):
                    # this device has just became ready, i.e. we have obtained values for all the variables.
                    self.on_ready()
                    self.ready = True
                    self.send_to_frontend('ready')
                # 2) check the watchdog, i.e. decide if the device is responsive.
                self.watchdog.check()
                # 3) query all variables. The method will check if it is really needed, i.e. the last such
                #    "queryall" happened not too recently
                self.queryall()
                # 4) create a log line
                self.log()
                # 5) create and send telemetry information.
                if (time.monotonic() - self.lasttimes['telemetry']) > self.telemetry_interval:
                    tm = self.get_telemetry()
                    self.send_to_frontend('telemetry', data=tm)
                    self.lasttimes['telemetry'] = time.monotonic()
            except CommunicationError as ce:
                self.logger.error(
                    'Communication error for device ' + self.name + ', exiting background process.')
                self.send_to_frontend('error', variablename=None, exception=ce,
                                      traceback=traceback.format_exc())
                exit_status = False  # abnormal termination
                break
            except WatchdogTimeout as wt:
                self.logger.error('Watchdog timeout for device ' + self.name + ', exiting loop.')
                self.send_to_frontend('error', variablename=None, exception=wt,
                                      traceback=traceback.format_exc())
                break
            except DeviceError as de:
                self.logger.error('DeviceError in the background process for {}: {}'.format(
                    self.name, traceback.format_exc()))
                self.send_to_frontend('error', variablename=None, exception=de, traceback=traceback.format_exc())
            except Exception as ex:
                self.logger.error('Exception in the background process for {}, exiting. {}'.format(
                    self.name, traceback.format_exc()))
                self.send_to_frontend('error', variablename=None, exception=ex, traceback=traceback.format_exc())
                exit_status = False  # abnormal termination
                break
            finally:
                if message is not None:
                    del message
        try:
            self.disconnect_device(because_of_failure=not exit_status)
            self.finalize_after_disconnect()
        finally:
            self.logger.debug('Background process ending for {}. Messages sent: {:d}. Messages received: {:d}.'.format(
                self.name, self.counters['outmessages'], self.counters['inmessages']))
            for h in self.logger.handlers[:]:
                self.logger.removeHandler(h)
            self.send_to_frontend('exited', normaltermination=exit_status)
        return exit_status

    def dispatch_inqueue_message(self, message):
        exit_status = False
        if message['type'] == 'config':
            self.config = message['configdict']
        elif message['type'] == 'exit':
            exit_status = True  # normal termination
            raise ExitWorkerLoop(True)
        elif message['type'] == 'query':
            if message['signal_needed']:
                try:
                    self.refresh_requested[message['name']] += 1
                except KeyError:
                    self.refresh_requested[message['name']] = 1
            self.lasttimes['query'] = time.monotonic()
            self.query_variable(message['name'])
        elif message['type'] == 'set':
            # the following command can raise a ReadOnlyVariable exception
            self.set_variable(message['name'], message['value'])
        elif message['type'] == 'execute':
            self.execute_command(message['name'], message['arguments'])
        elif message['type'] == 'communication_error':
            self.send_to_frontend('error', variablename=None,
                                  exception=message['exception'],
                                  traceback=message['traceback'])
            raise message['exception']
        elif message['type'] == 'timeout':
            pass
            # do nothing yet, a communication_error message will follow.
        elif message['type'] == 'incoming':
            self.lasttimes['recv'] = message['timestamp']
            self.counters['inmessages'] += 1
            try:
                self.process_incoming_message(message=message['message'],
                                              original_sent=message['sent_message'])
            except InvalidMessage as exc:
                self.send_to_frontend('error', variablename=None,
                                      exception=exc,
                                      traceback=traceback.format_exc())
                self.query_requested.clear()
        elif message['type'] == 'log':
            self.send_to_frontend('log', logrecord=message['logrecord'])
        elif message['type'] == 'send_complete':
            # sending of a message finished.
            self.lasttimes['send'] = message['timestamp']
        else:
            raise ValueError(
                'Unknown command for background worker: {}'.format(message['type']))
        return exit_status

    def connect_device(self):
        """Connect to the device. This consists of the following steps:
        1) ensuring a sane environment: the connection is not yet established.
            Typically: "assert not self.get_connected()"
        2) establish tcp, modbus, serial, whatever connection by calling
            `self.establish_connection`

        Connection and communication parameters (e.g. host, port, baud rate,
        timeout etc.) have been already given in the constructor of this class.

        Any exceptions are passed through to the caller.
        """
        assert not self.get_connected()
        self.logger.debug('Connecting to device ' + self.name)
        self.establish_connection()
        self.logger.debug('Connection to device {} established. Running initialization.'.format(self.name))
        self.initialize_after_connect()
        self.logger.debug('Device {} initialized.'.format(self.name))

    def disconnect_device(self, because_of_failure: bool = False):
        """Disconnect from the device. This consists of the following steps:
        1) ensure that the environment is sane: the connection is established
        3) run _finalize_after_disconnect
        4) close socket/modbus/whatever

        Note that disconnecting can be unexpected, i.e. due to a communications
        failure or because of the remote end. In this case this function is
        called on a queue message from the backend.
        """
        if not self.get_connected():
            return
        self.logger.debug('Disconnecting from device' +
                          ['', ' because of a failure'][because_of_failure])
        self.breakdown_connection()
        self.logger.debug('Connection broken down.')
        self.finalize_after_disconnect()
        self.logger.debug('Finalized')

    def get_telemetry(self):
        """Get telemetry data"""
        tm = TelemetryInfo()
        tm.last_queryall = time.monotonic() - self.lasttimes['queryall']
        tm.last_recv = time.monotonic() - self.lasttimes['recv']
        tm.last_query = time.monotonic() - self.lasttimes['query']
        tm.last_send = time.monotonic() - self.lasttimes['send']
        tm.watchdog = self.watchdog.elapsed()
        tm.watchdog_active = self.watchdog.active
        tm.watchdog_timeout = self.watchdog.timeout
        tm.message_instances = Message.instances
        tm.missing_variables = ', '.join([v for v in self.all_variables if v not in self.properties])
        tm.busy_level = self.is_busy()
        tm.outstanding_queries = ', '.join([k for k in sorted(self.query_requested)])
        tm.status = self.properties['_status']
        tm.status_age = time.monotonic() - self.timestamps['_status']
        return tm

    def update_variable(self, varname: str, value: object, force: bool = False) -> bool:
        """Check if the new value (`value`) of the variable `varname` is different
        from the previous one.

        Also sends an 'update' message to the frontend in any of the following cases:

        1) If the new value is different (i.e. not ==) from the old one
        2) If force is True
        3) If the variable name is in `self.refresh_requested`

        Regardless that the value changed or not, the corresponding timestamp is updated
        in `self.timestamps`

        The function returns True if an 'update' message was queued, and False
        otherwise.
        """
        # first of all, pat the watchdog.
        self.watchdog.pat()
        try:
            # remove the query request of this variable, if any.
            del self.query_requested[varname]
        except KeyError:
            pass
        try:
            if self.properties[varname] != value:
                raise KeyError(varname)  # we raise a KeyError, signalling that the variable has to be updated.
            if force:
                raise KeyError(varname)
            if varname in self.refresh_requested and self.refresh_requested[varname] > 0:
                self.logger.debug(
                    'Refresh_requested for variable {} was {:d}'.format(varname, self.refresh_requested[varname]))
                self.refresh_requested[varname] -= 1
                raise KeyError(varname)
            return False
        except KeyError:
            #            self._logger.debug('Setting {} for {} to {}'.format(varname, self.name, value))
            self.properties[varname] = value
            self.send_to_frontend('update', name=varname, value=value)
            return True
        finally:
            # set the timestamp
            self.timestamps[varname] = time.monotonic()

    def log(self):
        """Write a line in the log-file, according to `self.log_formatstr`.
        """
        if (not self.logfile) or (not self.log_formatstr):
            return
        with open(self.logfile, 'a+', encoding='utf-8') as f:
            try:
                f.write('{:.3f}'.format(time.time()) + '\t' +
                        self.log_formatstr.format(**self.properties) + '\n')
            except KeyError as ke:
                if self.ready:
                    self.logger.warn('KeyError while producing log line for {}: {}'.format(
                        self.name, ke.args[0]))

    def queryall(self):
        """Initiate a query on all variables"""
        if (time.monotonic() - self.lasttimes['queryall']) < self.queryall_interval:
            # do not query all variables too frequently
            return
        self.lasttimes['queryall'] = time.monotonic()

        if (self.urgency_modulo == 0) or (self.counters['queryalls'] % self.urgency_modulo):
            # only query urgent variables
            if self.urgent_variables is not None:
                querylist = self.urgent_variables
            else:
                querylist = self.minimum_query_variables
        else:
            # query all variables
            querylist = self.minimum_query_variables
        # remove constant variables
        querylist = [v for v in querylist if v not in self.constant_variables]
        # add missing variables
        querylist.extend([v for v in self.get_missing_variables() if v not in querylist])
        assert isinstance(querylist, list)
        for vn in querylist:
            self.queryone(vn)
        return

    def queryone(self, variablename: str, force: bool = False) -> bool:
        """Queries the value of a state variable.

        The actual job is done by query_variable, which has to be overridden
        in subclasses. Please do not override this method.

        Returns:
            True if a query has been done
            False otherwise.
        """
        try:
            if force:
                self.logger.debug('Forced queryone for variable {}'.format(variablename))
                if variablename not in self.refresh_requested:
                    self.refresh_requested[variablename] = 0
                self.refresh_requested[variablename] += 1
            elif ((self.query_requested[variablename] - time.monotonic()) < self.query_timeout):
                # This mechanism avoids re-querying the variable until a value
                # has been obtained for it, or until a very long time
                # (self.query_timeout) has passed
                return False
            else:
                try:
                    raise DeviceError('Query timeout on variable {} in device {}'.format(variablename, self.name))
                except DeviceError as de:
                    self.send_to_frontend(
                        'error', variablename=variablename,
                        exception=de, traceback=traceback.format_exc())
            raise KeyError(variablename)
        except KeyError as ke:
            assert ke.args[0] == variablename
            self.query_requested[variablename] = time.monotonic()
            self.lasttimes['query'] = time.monotonic()
            if variablename in ['_status', '_auxstatus']:
                self.update_variable(variablename, self.properties[variablename])
            elif not self.query_variable(variablename):
                try:
                    del self.query_requested[variablename]
                except KeyError:
                    # this can happen if self.query_requested[variablename] has already been deleted, e.g. because
                    # self.query_variable() calls self.update_variable() directly.
                    pass
                return False
            return True

    def query_variable(self, variablename: str) -> bool:
        """Queries the value of the current variable. This should typically be
        overridden in derivative classes.

        Notes:

        1) some devices, e.g. the pilatus300k can become unresponsive when doing
        work (exposing multiple images). In these cases, this function must
        refrain from the actual querying. If the device is in unresponsive state,
        can be decided by checking the '_status' state variable.

        2) some devices use blocking connections (synchronous operation), i.e. a
        query gives results immediately. In this case, this function is responsible
        to call `update_variable`. Other devices are asynchronous, i.e. a query command
        has to be sent, to which the device will reply in turn. In this case, the
        reply will come in a form of an 'incoming' message to `inqueue`,
        and `update_variable` must be called from the `process_incoming_message`
        method.

        Returns:
            True if the query has been sent successfully AND reply is expected
                from the device.
            False if for some reason you cannot start the query, AND
                self.update_variable is not expected to be called any time soon.
            True if the new value of the variable has been determined in this
                method AND self.update_variable has been called.
        """
        raise NotImplementedError

    def set_variable(self, variable: str, value: object):
        """Initiate setting a device status variable by contacting the device.

        Abstract method: override this in subclasses. What you should do:

        1) check if the variable is writable. If not, raise a ReadOnlyVariable
        exception

        2) check the validity of the value is checked (range, domain, etc.).
        You can take into account the values of already read variables in
        self.properties. If the value is invalid, an InvalidValue exception
        must be raised.

        3) ensure that an 'update' message will be sent to the front-end after
        setting the variable:
        a) In case of synchronous devices, this function must update the
        variable by requesting its value from the device and calling
        `self.update_variable(..., force=True)`.
        b) In case of asynchronous devices, you can do several things:
        - queue a query request for the variable into the `inqueue`. This will
            ensure that even if the value is not changed, the variable will be
            re-queried and the frontend notified of an update.
        - leave the notification of the front-end to the next query-all run.
            Note however, that if the set is a no-op (the new value is the same
            as the old one), an automatic query won't send notification to the
            frontend. Thus in this case you must first check if the current
            value is the same as the new one, and if yes, do not send anything
            to the device, but send an 'update' notification to the frontend.
            Contact the device only if the new value is different from the old
            one.
        """
        raise NotImplementedError

    def execute_command(self, commandname: str, arguments: tuple):
        """Initiate the execution of a command by contacting the device. In a
        similar fashion as `set_variable`, you must raise InvalidValue
        exceptions on argument validity errors, and ensure the notification of
        the front-end thread on the starting and ending of the command. The
        recommended way of doing this is to change the '_status' state variable
        (e.g. 'idle' -> 'busy' -> 'idle'), and notify the front-end.
        """
        raise NotImplementedError

    def process_incoming_message(self, message: bytes, original_sent: bytes = None):
        """In case of asynchronous devices, this method is called whenever a
        message arrives from the device. After processing the message, it must
        call 'self.update_variable' with the obtained new value(s).

        The argument `message` is the message as received from the device,
        an instance of `bytes`. The actual subclass of Device, which is
        responsible for the way of communication (TCP, RS232, Modbus, etc.),
        must ensure that this is a single and complete message.

        `original_sent` is the message sent to the device, to which `message`
        is a reply. It is also an instance of `bytes`.
        """
        raise NotImplementedError

    def on_ready(self):
        """Called when the startup is done, i.e. all variables
        have been read."""
        return True

    def initialize_after_connect(self):
        pass

    def finalize_after_disconnect(self):
        pass

    def get_connected(self) -> bool:
        """Check if the device is connected.

        Abstract method: override this in subclasses.

        """
        raise NotImplementedError

    def establish_connection(self):
        """Establish a connection to the device.

        Abstract method: override this in subclasses.

        Raise an exception if the connection cannot be established.

        If you override this, you can safely assume that no connection
        exists to the device.

        Connection and communication parameters are found in
        self.deviceconnectionparameters
        """
        raise NotImplementedError

    def breakdown_connection(self):
        """Break down the connection to the device.

        Abstract method: override this in subclasses.

        Should not raise an exception.

        This method can safely assume that a connection exists to the
        device.
        """
        raise NotImplementedError

    @classmethod
    def create_and_run(cls, *args, **kwargs):
        """Target function for multiprocessing.Process, which instantiates this
        background class and calls its worker function."""
        obj = cls(*args, **kwargs)
        result = obj.worker()
        del obj
        return result
