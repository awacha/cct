import logging
import multiprocessing
import queue
import select
import socket
import time
import traceback
from logging.handlers import QueueHandler

from .backend import DeviceBackend
from .exceptions import DeviceError, CommunicationError
from .message import Message

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class QueueLogHandler(QueueHandler):
    def prepare(self, record):
        return Message('log', 0, 'logger', logrecord=record)


class TCPCommunicator:
    """A class to perform direct communications over TCP/IP with the hardware.

    This class should be instantiated in a separate, dedicated process.
    Communication with the other parts of the program is done through queues
    (multiprocessing.Queue). Messages are similar dictionaries as in
    DeviceBackend, with the following required fields:

    'type' (str): the type of the message
    'source' (str): the unique identifier of the source of the message
    'id' (int): a unique integer ID, increasing
    'timestamp': the value of time.monotonic() at the generation of the message

    The allowed incoming message type:

    'send': send a message
        'message' (bytes): the message to be send, in the correct format the
            device can accept. It will be sent without modifications.
        'expected_replies' (int): the number of expected replies
        'timeout' (float): the time in seconds, after which the replies are
            considered lost
        'asynchronous' (bool): if other messages can be sent before the reply
            to this message arrives. This is ignored if `expected_replies` is
            zero.

    This process sends the following types:

    'incoming': a message has been received
        'message' (bytes): the message received
        'sent_message' (bytes): the message originally sent
        'reply_count' (int): from the expected N replies, which this is
        'referred_id': the ID of the corresponding incoming queue message
    'send_complete': sending a message completed
        'message' the message just sent.
        'referred_id': the ID of the corresponding incoming queue message
    'timeout': waiting for a reply timed out.
        'message (bytes): the message sent
        'received_replies (int)': the replies we received
        'referred_id': the ID of the corresponding incoming queue message.
    'communication_error': some error happened
        'exception' (Exception): the exception instance
        'traceback' (str): the traceback formatted with traceback.format_exc()

    Because stopping must be a high priority event, the parent process can
    request this process to terminate by setting a kill flag. The parent is not
    allowed to feed anything into the input queue of the process after setting
    this flag. After seeing the kill flag set, this process flushes its input
    queue, closes the connection to the hardware, sends an 'exited' message to
    the output queue ('normaltermination': True) and terminates.

    If a fatal error in communication happens, this process must close the
    communication channel to the hardware device and send an 'exited' message
    to the output queue ('normaltermination: False) and terminates. The parent
    thread is responsible to flush the input queue of this process.

    Note that non-solicited messages from the device are considered an error
    in this class.
    """

    def __init__(self, instancename, host, port, poll_timeout, sendqueue, incomingqueue,
                 killflag, exitedflag, getcompletemessages):
        self.name = instancename
        assert isinstance(sendqueue, multiprocessing.Queue)
        self.sendqueue = sendqueue
        assert isinstance(incomingqueue, multiprocessing.Queue)
        self.incomingqueue = incomingqueue
        self.poll_timeout = poll_timeout
        self.get_complete_messages = getcompletemessages
        self.logger = logging.getLogger(
            __name__ + '::' + instancename + '__tcpprocess')
        self.logger.propagate = False
        self.msgid_counter = 0
        self.killflag = killflag
        self.exitedflag = exitedflag
        if not self.logger.hasHandlers():
            self.logger.addHandler(QueueLogHandler(incomingqueue))
            self.logger.addHandler(logging.StreamHandler())
            self.logger.setLevel(logging.getLogger(__name__).getEffectiveLevel())
        self.logger.debug('Connecting over TCP/IP to device {}: {}:{:d}'.format(self.name, host, port))
        try:
            self.tcpsocket = socket.create_connection((host, port))
            self.tcpsocket.setblocking(False)
        except (socket.error, socket.gaierror, socket.herror, ConnectionRefusedError) as exc:
            logger.error(
                'Error initializing socket connection to device {}:{:d}'.format(host, port))
            try:
                del self.tcpsocket
            except AttributeError:
                pass
            self.send_to_backend('error', exception=exc, traceback=traceback.format_exc())
            self.send_to_backend('exited', normaltermination=False)
            raise DeviceError('Cannot connect to device.', exc)

        self.message_part = b''
        self.lastsent = []  # a stack of recently sent messages.
        self.lastsendtime = 0
        self.cleartosend = True

    def send_to_backend(self, msgtype, **kwargs):
        self.msgid_counter += 1
        msg = Message(msgtype, self.msgid_counter, self.name + '__tcpprocess', **kwargs)
        self.incomingqueue.put_nowait(msg)

    def send_message_to_device(self):
        """Send a message from the sending queue to the device.

        Before sending, check the cleartosend semaphore. If it cannot be acquired, no message is sent.
        """
        if not self.cleartosend:
            # Do not send a message to the device if we are not allowed to.
            return False
        # otherwise we are clear to send a message, not expecting a response from the device.
        # get the next job
        try:
            msg = self.sendqueue.get_nowait()
        except queue.Empty:
            # no message to send
            return False
        assert isinstance(msg, Message)
        assert msg['type'] == 'send'
        # we have to send a message.
        self.cleartosend = False
        chars_sent = 0
        outmsg = msg['message']
        while chars_sent < len(outmsg):
            justsent = self.tcpsocket.send(outmsg[chars_sent:])
            assert justsent > 0
            chars_sent += justsent
        # the message has been sent.
        if msg['expected_replies'] > 0:
            # if we are expecting replies, save `msg` to the last sent stack.
            msg['sendtime'] = time.monotonic()
            msg['received_replies'] = 0
            self.lastsent.append(msg)
        else:
            # we are not expecting replies
            self.cleartosend = True
        if msg['asynchronous']:
            # we can send another message before we obtain reply/replies.
            self.cleartosend = True
        self.send_to_backend('send_complete', message=outmsg)
        self.lastsendtime = time.monotonic()

    def receive_message_from_device(self, polling):
        """Try to receive a message from the device."""
        message = b''
        while True:
            # read all parts of the message.
            try:
                # check if an input is waiting on the socket
                sock, event = polling.poll(self.poll_timeout * 1000)[0]
            except IndexError:
                # no incoming message
                break  # the while True loop
            # an event on the socket is waiting to be processed
            if event & (select.POLLERR | select.POLLHUP | select.POLLNVAL):
                # fatal socket error, we have to close communications.
                raise CommunicationError(
                    'Socket is in exceptional state: {:d}'.format(event))
                # end watching the socket.
            # read the incoming message
            message = message + sock.recv(4096)
            if not message:
                # remote end hung up on us
                raise CommunicationError(
                    'Socket has been closed by the remote side')
        # append the currently received message to the previously received,
        # incomplete message, if any
        self.message_part = self.message_part + message
        if self.message_part:
            self.message_part = self.dispatch_message(self.message_part)
        # Otherwise, if 'message' is empty, it means that no message has been
        # read, because no message was waiting. Note that this is not the same
        # as receiving an empty message, which signifies the breakdown of the
        # communication channel. This case has been handled above, in the
        # while loop.
        return

    def dispatch_message(self, message: bytes) -> bytes:
        if message:
            # The incoming message is ready, send it to the incoming queue.
            # First dissect the message into different parts, if needed.
            messages = self.get_complete_messages.__call__(self.message_part)
            for message in messages[:-1]:
                if not self.lastsent:
                    # this is an unsolicited message from the device.
                    raise CommunicationError('Unsolicited message from device {}: {}'.format(self.name, str(message)))
                self.send_to_backend('incoming', message=message, sent_message=self.lastsent[-1]['message'],
                                     referred_id=self.lastsent[-1]['id'],
                                     reply_count=self.lastsent[-1]['received_replies'])
                self.lastsent[-1]['received_replies'] += 1
                if self.lastsent[-1]['expected_replies'] == self.lastsent[-1]['received_replies']:
                    del self.lastsent[-1]
                if not self.lastsent:
                    # if no messages are waiting for replies:
                    self.cleartosend = True
                elif self.lastsent[-1]['asynchronous']:
                    # if the next message we are expecting a reply for is asynchronous,
                    # we can send another message.
                    self.cleartosend = True
                else:
                    # leave self.cleartosend as is.
                    pass
            return messages[-1]
        else:
            return b''

    def run(self):
        """Background process for communication."""
        self.exitedflag.clear()
        polling = select.poll()
        polling.register(self.tcpsocket, select.POLLIN | select.POLLPRI |
                         select.POLLERR | select.POLLHUP | select.POLLNVAL)
        try:
            while True:
                if self.killflag.is_set():
                    break
                self.send_message_to_device()
                self.receive_message_from_device(polling)
                if self.lastsent:
                    if time.monotonic() - self.lastsent[-1]['sendtime'] > self.lastsent[-1]['timeout']:
                        self.send_to_backend('timeout', message=self.lastsent[-1]['message'],
                                             received_replies=self.lastsent[-1]['received_replies'],
                                             referred_id=self.lastsent[-1]['id'])
                    raise CommunicationError('Reply timeout. Last sent: {}'.format(self.lastsent[-1]['message']))
        except Exception as exc:
            self.send_to_backend('communication_error', exception=exc, traceback=traceback.format_exc())
        finally:
            # the next line is to avoid a deadlock situation where this process cannot end until the parent process
            # get-ted all messages from the incomingqueue.
            self.incomingqueue.cancel_join_thread()
            polling.unregister(self.tcpsocket)
            self.tcpsocket.shutdown(socket.SHUT_RDWR)
            self.tcpsocket.close()
            del self.tcpsocket
            while True:
                try:
                    self.sendqueue.get_nowait()
                except queue.Empty:
                    break
            self.logger.debug('Exiting TCP backend for ' + self.name)
            self.exitedflag.set()

    @classmethod
    def create_and_run(cls, name, host, port, poll_timeout, sendqueue, incomingqueue, killflag, exitedflag,
                       getcompletemessages):
        """Can be used as a target function of multiprocessing.Process"""
        tcpcomm = cls(name, host, port, poll_timeout, sendqueue, incomingqueue, killflag, exitedflag,
                      getcompletemessages)
        tcpcomm.run()


# noinspection PyAbstractClass
class DeviceBackend_TCP(DeviceBackend):
    """Device with TCP socket connection.

    After the socket has been connected, a background process is started,
    which takes care of read/write operations on the socket. You can think
    of this as a secondary back-end process. Typically, the front-end process
    will communicate with the primary back-end through `_queue_to_frontend`
    and `_queue_to_backend`, and the two back-ends communicate via
    `_outqueue` and `_queue_to_backend`.

    Interactions with the device are primarily initiated by the front-end,
    managed by the primary back-end and carried out by the communication
    back-end.
    """

    reply_timeout = 1

    outqueue_query_limit = 10  # skip query all if the outqueue is larger than this limit

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tcp_outqueue = multiprocessing.Queue()
        self.poll_timeout = None
        self.killflag = multiprocessing.Event()
        self.tcpprocess_exited = multiprocessing.Event()
        self.tcp_communicator = None

    def get_telemetry(self):
        tm = super().get_telemetry()
        tm.sendqueuelen = self.tcp_outqueue.qsize()
        return tm

    @staticmethod
    def get_complete_messages(message):
        """Check if the received message is complete. All devices signify the
        end of a message in some way: either by using fixed-length messages,
        or by a sentinel character at the end.

        This method should split `message`, a bytes instance into complete
        messages. It should return a list of bytes objects, the last being
        an incomplete message.

        For example:

        1) mostly `message` will be a single, complete message. This method
        then must return `[message, b'']`.

        2) if `message` is a single, incomplete message, this method should
        return `[message]`.

        3) if `message` contains two or more complete messages with an
        incomplete one at the end, the return value must be
        `[message1, message2, message3, ... , message_incomplete]`.

        4) if `message` consists of two or more complete messages,
        `[message1, message2, message3, ..., b'']` must be returned.

        To summarize: the last item of the returned list must always be
        an incomplete message or an empty bytes string.

        Note: if subclassing this abstract method, you can only use the value
        of `message`, and should not access any other outside data, because
        this method is called from a different process (not the foreground and
        not the background process)"""
        raise NotImplementedError

    def get_connected(self) -> bool:
        """Check if the device is connected.
        """
        if self.tcp_communicator is None:
            return False
        assert isinstance(self.tcp_communicator, multiprocessing.Process)
        return self.tcp_communicator.is_alive()

    def establish_connection(self):
        """Establish a connection to the device.

        Raises an exception if the connection cannot be established.
        """
        self.killflag.clear()
        self.tcp_communicator = multiprocessing.Process(name=self.name + '__tcpcommunicator',
                                                        target=TCPCommunicator.create_and_run,
                                                        args=(self.name,
                                                              self.deviceconnectionparameters[0],
                                                              self.deviceconnectionparameters[1],
                                                              self.deviceconnectionparameters[2],
                                                              self.tcp_outqueue,
                                                              self.inqueue,
                                                              self.killflag, self.tcpprocess_exited,
                                                              self.get_complete_messages))
        self.tcp_communicator.daemon = True
        self.tcp_communicator.start()

    def breakdown_connection(self):
        """Break down the connection to the device.

        Abstract method: override this in subclasses.

        Should not raise an exception.

        This method can safely assume that a connection exists to the
        device.
        """
        self.killflag.set()
        self.logger.info('Waiting for TCP communication process of {} to exit'.format(self.name))
        self.tcpprocess_exited.wait()
        self.logger.debug('Join-ing TCP communication process of {}'.format(self.name))
        self.tcp_communicator.join()
        self.tcp_communicator = None
        self.logger.info('TCP communication process of {} exited'.format(self.name))

    def send_message(self, message, expected_replies=1, timeout=None, asynchronous=False):
        if timeout is None:
            timeout = self.reply_timeout
        self.counters['outmessages'] += 1
        msg = Message('send', self.counters['outmessages'], self.name + '__backend', message=message,
                      expected_replies=expected_replies, timeout=timeout, asynchronous=asynchronous)
        self.tcp_outqueue.put_nowait(msg)

    def queryall(self):
        if self.outqueue.qsize() > self.outqueue_query_limit:
            # do not query all if there are too many messages waiting to be sent to the device.
            return
        return super().queryall()

