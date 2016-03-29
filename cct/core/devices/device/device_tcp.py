import logging
import multiprocessing
import queue
import select
import socket
import sys
import time

from .device import Device
from .exceptions import DeviceError, CommunicationError

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class TCPCommunicator(multiprocessing.Process):
    def __init__(self, tcpsocket, sendqueue, incomingqueue, poll_timeout, cleartosend_semaphore, getcompletemessages):
        super().__init__()
        self._tcpsocket=tcpsocket
        self._sendqueue=sendqueue
        self._incomingqueue=incomingqueue
        self._poll_timeout=poll_timeout
        self._cleartosend_semaphore=cleartosend_semaphore
        self._get_complete_messages=getcompletemessages
        self._message=b''
        self._lastsent=[]

    def _send_to_backend(self, msgtype, **kwargs):
        msg={'type':msgtype,'id':0,'timestamp':time.monotonic()}
        msg.update(kwargs)
        self._incomingqueue.put_nowait(msg)

    def _send_message_to_device(self):
        if not self._cleartosend_semaphore.acquire(block=False):
            # Do not send a message to the device if we are not allowed to.
            # We acquire the semaphore for sending, and the background process
            # should release it when it has processed the returned results.
            return
        try:
            command, outmsg, expected_replies = self._sendqueue.get_nowait()
            if command == 'send':
                sent = 0
                while sent < len(outmsg):
                    sent += self._tcpsocket.send(outmsg[sent:])
                for i in range(expected_replies):
                    self._lastsent.insert(0,outmsg)
                if expected_replies==0:
                    # we do not expect a reply, so we release the
                    # cleartosend semaphore
                    self._cleartosend_semaphore.release()
            elif command == 'exit':
                raise StopIteration
        except queue.Empty:
            pass

    def _receive_message_from_device(self, polling):
        message=b''
        while True:
            # read all parts of the message.
            try:
                # check if an input is waiting on the socket
                socket, event = polling.poll(self._poll_timeout * 1000)[0]
            except IndexError:
                # no incoming message
                break  # this inner while True loop
            # an event on the socket is waiting to be processed
            if (event & (select.POLLERR | select.POLLHUP | select.POLLNVAL)):
                # fatal socket error, we have to close communications.
                raise CommunicationError(
                    'Socket is in exceptional state: %d' % event)
                # end watching the socket.
            # read the incoming message
            message = message + self._tcpsocket.recv(4096)
            if not message:
                # remote end hung up on us
                raise CommunicationError(
                    'Socket has been closed by the remote side')
        # append the currently received message to the previously received,
        # incomplete message, if any
        self._message=self._message+message
        if self._message:
            # the incoming message is ready, send it to the background
            # thread
            messages=self._get_complete_messages(self._message)
            for message in messages[:-1]:
                self._send_to_backend('incoming', message=message, sent=self._lastsent.pop())
            self._message=messages[-1]
        # Otherwise, if 'message' is empty, it means that no message has been
        # read, because no message was waiting. Note that this is not the same
        # as receiving an empty message, which signifies the breakdown of the
        # communication channel. This case has been handled above, in the
        # while loop.
        return

    def run(self):
        """Background process for communication."""
        polling = select.poll()
        polling.register(self._tcpsocket, select.POLLIN | select.POLLPRI |
                         select.POLLERR | select.POLLHUP | select.POLLNVAL)
        try:
            while True:
                try:
                    self._send_message_to_device()
                except StopIteration:
                    break
                self._receive_message_from_device(polling)

        except Exception as exc:
            self._send_to_backend('communication_error', exception=exc, traceback=sys.exc_info()[2])

        finally:
            polling.unregister(self._tcpsocket)


class Device_TCP(Device):
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

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)
        self._outqueue = multiprocessing.Queue()
        self._poll_timeout = None

    def _get_connected(self):
        """Check if we have a connection to the device. You should not call
        this directly."""
        return hasattr(self, '_tcpsocket')

    def _get_complete_messages(self, message):
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

    def _establish_connection(self):
        host, port, socket_timeout, poll_timeout = self._connection_parameters
        self._logger.debug('Connecting over TCP/IP to device %s: %s:%d' % (self.name, host, port))
        try:
            self._tcpsocket = socket.create_connection(
                (host, port), socket_timeout)
            self._tcpsocket.setblocking(False)
            self._poll_timeout = poll_timeout
        except (socket.error, socket.gaierror, socket.herror, ConnectionRefusedError) as exc:
            self._logger.error(
                'Error initializing socket connection to device %s:%d' % (host, port))
            raise DeviceError('Cannot connect to device.',exc)
        self._flushoutqueue()
        self._cleartosend_semaphore=multiprocessing.BoundedSemaphore(1)
        self._communication_subprocess = TCPCommunicator(
            self._tcpsocket, self._outqueue, self._queue_to_backend, self._poll_timeout, self._cleartosend_semaphore,
            self._get_complete_messages)
        self._communication_subprocess.daemon=True
        self._communication_subprocess.start()
        self._logger.debug(
            'Communication subprocess started for device %s:%d' % (host, port))

    def _breakdown_connection(self):
        self._outqueue.put_nowait(('exit', None, None))
        try:
            self._communication_subprocess.join()
        except AssertionError:
            pass
        del self._communication_subprocess
        self._tcpsocket.shutdown(socket.SHUT_RDWR)
        self._tcpsocket.close()
        self._flushoutqueue()
        del self._tcpsocket

    def _flushoutqueue(self):
        while True:
            try:
                self._outqueue.get_nowait()
            except queue.Empty:
                break

    def _send(self, message, expected_replies=1):
        """Send `message` (bytes) to the device.

        If the number of expected replies is not one, also give it.
        """
        # self._logger.debug('Sending message %s' % str(message))
        self._outqueue.put_nowait(('send', message, expected_replies))
        self._count_outmessages+=1
