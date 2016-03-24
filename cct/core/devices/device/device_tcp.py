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
        self._communication_subprocess = multiprocessing.Process(
            target=self._communication_worker)
        self._communication_subprocess.daemon=True
        self._communication_subprocess.start()
        self._logger.debug(
            'Communication subprocess started for device %s:%d' % (host, port))

    def _breakdown_connection(self):
        self._outqueue.put_nowait(('exit', None))
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

    def _send(self, message):
        """Send a message (bytes) to the device"""
        # self._logger.debug('Sending message %s' % str(message))
        self._outqueue.put_nowait(('send', message))
        self._lastsendtime = time.time()
        self._count_outmessages+=1

    def _communication_worker(self):
        """Background process for communication."""
        polling = select.poll()
        polling.register(self._tcpsocket, select.POLLIN | select.POLLPRI |
                         select.POLLERR | select.POLLHUP | select.POLLNVAL)
        try:
            while True:
                try:
                    command, outmsg = self._outqueue.get_nowait()
                    if command == 'send':
                        sent = 0
                        while sent < len(outmsg):
                            sent += self._tcpsocket.send(outmsg[sent:])
                    elif command == 'exit':
                        break
                except queue.Empty:
                    pass
                message = b''
                while True:
                    # read all parts of the message.
                    try:
                        # check if an input is waiting on the socket
                        socket, event = polling.poll(
                            self._poll_timeout * 1000)[0]
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
                if not message:
                    # no message was read, because no message was waiting. Note that
                    # we are not dealing with an empty message, which would signify
                    # the breakdown of the communication channel.
                    continue
                # the incoming message is ready, send it to the background
                # thread
                self._send_to_backend('incoming',message=message)
        except CommunicationError as exc:
            self._send_to_backend('communication_error',exception=exc,traceback=sys.exc_info()[2])
        except Exception as exc:
            try:
                raise CommunicationError(exc)
            except CommunicationError as exc:
                self._send_to_backend('communication_error',exception=exc,traceback=sys.exc_info()[2])
        finally:
            polling.unregister(self._tcpsocket)
