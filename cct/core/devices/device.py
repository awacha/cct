import logging
import multiprocessing
import os
import queue
import resource
import select
import socket
import time
import traceback
from logging.handlers import QueueHandler

from gi.repository import GLib, GObject
from pyModbusTCP.client import ModbusClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DeviceError(Exception):
    pass


class CommunicationError(DeviceError):
    pass


class QueueLogHandler(QueueHandler):
    def prepare(self, record):
        return ('_log', record)


class Device(GObject.GObject):
    """The abstract base class of a device, i.e. a component of the SAXS
    instrument, such as an X-ray source, a motor controller or a detector.

    The interface to a device consists of two parts: the first one runs in
    the front-end process, i.e. that of running the GUI. The other one is a
    background process, which takes care of the communication between the
    hardware.

    Properties (such as high voltage, shutter state for an X-ray source)
    are stored in `self._properties`, which must be queried by the front-end
    only through get_variable() and set_variable(). The names beginning with
    underscores ('_') are reserved for internal use.

    A refresh of a property can be initiated by sending `('query', <name>,
    None)` through `_queue_to_backend`. The back-end will reply to this by 
    `(<name>, <new value>)` in due course in `queue_to_frontend`. The value
    is also updated in `self._properties` by the back-end. If an exception
    occurs when reading the new value, `<new value>` will be an exception
    object, which the front-end thread should handle or re-raise.

    Properties can be refreshed periodically, automatically. If such a refresh
    happens and a change in the value occurs, the back-end sends `(<name>, 
    <new value>)` through `_queue_to_frontend`

    On the front-end side, an idle function is running, which takes care of
    reading `_queue_to_frontend` and emit-ing variable-change signals.

    In summary, the front-end can send the following types of messages through
    `_queue_to_backend` to the back-end:

    - ('query', <variable name>, None)
    - ('set', <variable name>, <new value>)
    - ('execute', <command name>, <tuple of arguments>)
    - ('exit', None, None)

    In addition, the backend can also get the following messages from other
    sources:

    - ('communication_error', None, None): this will be forwarded to the 
        front-end as ('_error', 'Communication error'). The front-end will
        have to call `disconnect_device(because_of_failure=True)`.
    - ('incoming', None, <incoming message from device>)  


    The back-end can send back the following types of messages through
    `_queue_to_frontend`:

    - (<variable name>, <new value>)
    - ('_error', <exception object>) if the exception cannot be associated to any
        variable.
    - ('_error', 'Communication error') if the communication channel with the
        device broke down and a formal disconnect is needed.

    Note: from the background process, we cannot:
        - access the GUI
        - emit signals
        - call functions which do one or more of the above.
    """
    __gsignals__ = {
        # emitted if the value of a variable changes. The first argument is the
        # name of the variable, the second is its new value
        'variable-change': (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
        # emitted if an error happens. The first argument is the the name of the
        # affected variable or '' if no variable corresponds to this error.
        # The second argument is an exception object. The third one is the
        # formatted traceback.
        'error': (GObject.SignalFlags.RUN_LAST, None, (str, object, str)),
        # emitted on (sudden) disconnect. The boolean argument is True if the
        # disconnection was unintentional
        'disconnect': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
        # emitted when the starup is done, i.e. all variables have been read at
        # least once
        'startupdone': (GObject.SignalFlags.RUN_FIRST, None, ()),
        # emitted when a response for a telemetry request has been received.
        # The argument is a dict.
        'telemetry': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    backend_interval = 1

    watchdog_timeout = 10

    log_formatstr = None

    def __init__(self, instancename, logdir='log', configdir='config', configdict=None):
        GObject.GObject.__init__(self)
        if not hasattr(self, '_logger'):
            # do not override _loggers set by children classes.
            self._logger = logger
        self.logdir = logdir
        self.configdir = configdir
        self.logfile = os.path.join(self.logdir, instancename + '.log')
        if configdict is not None:
            self.config = configdict
        else:
            self.config = {}
        self._instancename = instancename
        self._outstanding_telemetry = False
        self._properties = {'_status': 'Disconnected', '_auxstatus':None}
        self._timestamps = {'_status': time.time(), '_auxstatus':time.time()}
        self._queue_to_backend = multiprocessing.Queue()
        self._queue_to_frontend = multiprocessing.Queue()
        self._refresh_requested = {}
        self._background_startup_count=0
        self._ready=False
        # the backend process must be started only after the connection to the device
        # has been established.

    @property
    def name(self):
        return self._instancename

    def send_config(self, configdict):
        self._queue_to_backend.put_nowait(('config', None, configdict))
        self.config = configdict

    def _load_state(self, dictionary):
        """Load the state of this device to a dictionary."""
        self.log_formatstr = dictionary['log_formatstr']
        self.backend_interval = dictionary['backend_interval']

    def _save_state(self):
        """Write the state of this device to a dictionary and return it for
        subsequent saving to a file."""
        return {'log_formatstr': self.log_formatstr,
                'backend_interval': self.backend_interval}

    def _start_background_process(self):
        """Starts the background process and registers the queue-handler idle 
        function in the foreground"""
        if hasattr(self, '_idle_handler'):
            raise DeviceError('Background process already running')
        # empty the backend queue.
        while True:
            try:
                self._queue_to_backend.get_nowait()
            except queue.Empty:
                break
        self._ready=False
        self._outstanding_telemetry = False
        self._properties = {'_status': 'Disconnected','_auxstatus':None}
        self._timestamps = {'_status': time.time(),'_auxstatus':time.time()}
        self._refresh_requested = {}
        self._background_startup_count+=1
        self._background_process = multiprocessing.Process(
            target=self._background_worker, daemon=True, name='Background process for device %s' % self._instancename, args=(self._background_startup_count,))
        self._idle_handler = GLib.idle_add(self._idle_worker)
        self._background_process.start()
        self._logger.debug('Background process for %s has been started' %
                           self._instancename)

    def _stop_background_process(self):
        """Stops the background process and deregisters the queue-handler idle
        function in the foreground"""
        #if not hasattr(self, '_idle_handler'):
        #    raise DeviceError('Background process not running')
        try:
            self._queue_to_backend.put_nowait(('exit', None, None))
            self._background_process.join()
        except (AttributeError, AssertionError):
            pass
        try:
            del self._background_process
        except AttributeError:
            pass
        try:
            GLib.source_remove(self._idle_handler)
        except AttributeError:
            pass
        try:
            del self._idle_handler
        except AttributeError:
            pass

    def get_variable(self, name):
        """Get the value of the variable. If you need the most fresh value,
        connect to 'variable-change' and call `self.refresh_variable()`.
        """
        return self._properties[name]

    def set_variable(self, name, value):
        """Set the value of the variable. In order to ensure that the variable
        has really been updated, connect to 'variable-change' before calling
        this."""
        self._queue_to_backend.put_nowait(('set', name, value))
        self.refresh_variable(name)

    def list_variables(self):
        """Return the names of all currently defined properties as a list"""
        return list(self._properties.keys())

    def refresh_variable(self, name, check_backend_alive=True, signal_needed=True):
        """Request a refresh of the value of the named variable.

        check_backend_alive: before submitting the query to the backend, check
            if the backend process is running. If not, raise an exception.
            Usually you need this set to True. The raison d'etre of this switch
            is that there are some special cases upon initialization, when we
            are priming the queue before we start the backend.

        signal_needed: if you expect a variable-change signal even if no change
            occurred
        """
        if (not check_backend_alive) or self._background_process.is_alive():
            self._queue_to_backend.put_nowait(('query', name, signal_needed))
        else:
            raise DeviceError('Backend process not running')

    def execute_command(self, command, *args):
        """Execute a command on the device. The arguments are device dependent.

        Note that this may not be used for reading and writing device variables,
        the get_variable/set_variable mechanism is there for a reason.

        A typical usage case is starting or stopping an exposure, opening/closing
        the beam shutter or moving a motor.

        This function returns before the completion of the command. 
        """
        self._queue_to_backend.put_nowait(('execute', command, args))

    def _suppress_watchdog(self):
        """Suppresses checking for device inactivity. Some devices can
        become intentionally inactive for a long time, e.g. Pilatus
        when exposing multiple frames."""
        self._watchdog_alive = False

    def _release_watchdog(self):
        """Resumes checking for device inactivity"""
        self._watchdogtime = time.time()
        self._watchdog_alive = True

    def _on_background_queue_empty(self):
        if self._juststarted:
            if self._has_all_variables():
                self._queue_to_frontend.put_nowait(('_startup_done', None))
                self._on_startupdone()
                self._juststarted = False
        if ((time.time() - self._watchdogtime) > self.watchdog_timeout) and self._watchdog_alive:
            try:
                self._logger.error(
                    'Watchdog timeout in device %s. Last query was %f seconds ago.' % (
                    self._instancename, time.time() - self._lastquerytime))
                try:
                    self._logger.error('Last send was %f seconds ago.' % (time.time() - self._lastsendtime))
                except AttributeError:
                    pass
                try:
                    self._logger.error('Sendqueue length: %d'%self._sendqueue.qsize())
                except AttributeError:
                    pass
                self._logger.error('Number of outmessages: %d. Number of inmessages: %d'%(self._count_outmessages, self._count_inmessages))
                raise CommunicationError(
                    'Watchdog timeout: no message received from device %s. Last query was %f seconds ago.' % (
                    self._instancename, time.time() - self._lastquerytime))
            except CommunicationError as exc:
                self._queue_to_frontend.put_nowait(
                    ('_watchdog', (exc, traceback.format_exc())))
        if self._watchdog_alive:
            try:
                self._query_variable(None)  #query all variables
                self._lastquerytime = time.time()
            except CommunicationError as ce:
                self._logger.error('CommunicationError in background thread of %s: %s %s'%(self._instancename,ce,traceback.format_exc()))
                self._queue_to_frontend.put_nowait(('_error',(ce, traceback.format_exc())))
                raise
            except Exception as exc:
                self._logger.error('Other exception in background thread of %s: %s %s'%(self._instancename,exc,traceback.format_exc()))
                self._queue_to_frontend.put_nowait(
                    ('_error', (exc, traceback.format_exc())))
            else:
                self._log()  # log the values of variables

    def _on_start_backgroundprocess(self):
        """Called just before the infinite loop of the background process starts."""
        self._query_variable(None)
        self._lastquerytime = time.time()
        self._logger.debug('Starting background process for %s' % self._instancename)

    def _background_worker(self, startup_number):
        """Worker function of the background thread. The main job of this is
        to run periodic checks on the hardware (polling) and updating 
        `self._properties` accordingly, as well as writing log files.

        The communication between the front-end and back-end is only through
        `self._queue`. Note that a different copy of `self._properties`
        exists in each process, thus we cannot use it for communication.
        Please see the details in the class-level docstring.

        This is a general method, which should not be overloaded. The actual
        work is delegated to `_set_variable()`, `_execute_command()` and
        `_query_variable()`, which should be overridden case-by-case.
        """
        self._background_startup_count=startup_number
        self._logger = logging.getLogger(__name__ + '::' + self._instancename + '/backgroundprocess')
        self._logger.propagate = False
        self._count_queries=0
        self._count_inmessages=0
        self._count_outmessages=0
        if not self._logger.hasHandlers():
            self._logger.addHandler(QueueLogHandler(self._queue_to_frontend))
            self._logger.addHandler(logging.StreamHandler())
            self._logger.setLevel(logging.getLogger(__name__).getEffectiveLevel())
        # empty the properties dictionary
        self._properties = {}
        self._juststarted = True
        self._on_start_backgroundprocess()
        self._watchdogtime = time.time()
        self._watchdog_alive = True
        self._logger.info('Background thread started for %s, this is startup #%d'%(self._instancename, self._background_startup_count))
        while True:
            try:
                try:
                    cmd, propname, argument = self._queue_to_backend.get(
                        block=True, timeout=self.backend_interval)
                except queue.Empty:
                    self._on_background_queue_empty()
                    continue
                if cmd == 'config':
                    self.config = argument
                    self._on_background_queue_empty()

                elif cmd == 'telemetry':
                    tm = self._get_telemetry()
                    self._queue_to_frontend.put_nowait(('_telemetry', tm))
                    self._on_background_queue_empty()
                elif cmd == 'exit':
                    break  # the while True loop
                elif cmd in ['query']:
                    if propname not in self._refresh_requested:
                        self._refresh_requested[propname] = 0
                    if argument:
                        self._refresh_requested[propname] += 1
                    try:
                        self._query_variable(propname)
                        self._lastquerytime = time.time()
                    except CommunicationError as ce:
                        self._logger.error('CommunicationError in background thread of %s: %s %s'%(self._instancename,ce,traceback.format_exc()))
                        #self._queue_to_frontend.put_nowait(('_error',(ce, traceback.format_exc())))
                        raise
                    except Exception as exc:
                        self._logger.error('Other exception in background thread of %s: %s %s'%(self._instancename,exc,traceback.format_exc()))
                        self._queue_to_frontend.put_nowait(
                            (propname, (exc, traceback.format_exc())))

                elif cmd == 'set':
                    try:
                        self._set_variable(propname, argument)
                    except NotImplementedError as ne:
                        self._queue_to_frontend.put_nowait(
                            (propname, (ne, traceback.format_exc())))
                    except CommunicationError as ce:
                        raise
#                        self._queue_to_frontend.put_nowait(('_error',(ce, traceback.format_exc())))
                    except Exception as exc:
                        self._queue_to_frontend.put_nowait(
                            (propname, (exc, traceback.format_exc())))

                elif cmd == 'execute':
                    try:
                        self._execute_command(propname, argument)
                    except CommunicationError as ce:
                        #self._queue_to_frontend.put_nowait(('_error',(ce, traceback.format_exc())))
                        raise
                    except DeviceError as exc:
                        if len(exc.args)>1:
                            self._queue_to_frontend.put_nowait(
                                (exc.args[1], (exc, traceback.format_exc())))
                        else:
                            self._queue_to_frontend.put_nowait(('_error', (exc, traceback.format_exc())))
                    except Exception as exc:
                        self._queue_to_frontend.put_nowait(
                            ('_error', (exc, traceback.format_exc())))
                elif cmd == 'communication_error':
                    raise propname # raise the CommunicationError instance we got.
#                    self._queue_to_frontend.put_nowait((
#                        '_error', (propname, argument)))
                elif cmd == 'incoming':
                    self._count_inmessages+=1
                    try:
                        self._process_incoming_message(argument)
                    except CommunicationError as ce:
                        raise
                    except Exception as exc:
                        self._queue_to_frontend.put_nowait(
                            ('_error', (exc, traceback.format_exc())))
                else:
                    raise NotImplementedError(
                        'Unknown command for _background_worker: %s' % cmd)
            except CommunicationError as ce:
                self._logger.error('Communication error in the background thread for device %s, exiting loop.'%(self._instancename))
                self._queue_to_frontend.put_nowait(('_dead', (ce, traceback.format_exc())))
                break
            except Exception as ex:
                self._logger.error('Other exception in the background thread for device %s, exiting loop.'%(self._instancename))
                self._queue_to_frontend.put_nowait(('_dead', (ex, traceback.format_exc())))
                break
        self._logger.info('Background thread ending for device %s. Messages sent: %d. Messages received: %d.' % (self._instancename, self._count_outmessages, self._count_inmessages))

    def _get_telemetry(self):
        return {'processname': multiprocessing.current_process().name,
                'self': resource.getrusage(resource.RUSAGE_SELF),
                'children': resource.getrusage(resource.RUSAGE_CHILDREN),
                'inqueuelen': self._queue_to_backend.qsize()}

    def get_telemetry(self):
        if not self._outstanding_telemetry:
            self._queue_to_backend.put_nowait(('telemetry', None, None))
        else:
            raise DeviceError('Another telemetry request is pending.')

    def _has_all_variables(self):
        """Checks if all the variables have been requested and received at least once.
        The basic implementation just returns True. You should probably override this
        in the actual device."""
        return True

    def _on_startupdone(self):
        """Called from the backend thread when the startup is done, i.e. all variables
        have been read."""
        return True

    def _update_variable(self, varname, value, force=False):
        """Updates the value of the variable in _properties and queues a
        notification for the front-end thread. To be called from the back-end
        process. Returns True if the value really changed, False if not."""
        self._watchdogtime = time.time()
        try:
            assert(self._properties[varname] == value) # can raise AssertionError and KeyError
            if force:
                raise KeyError
            if varname in self._refresh_requested and self._refresh_requested[varname] > 0:
                self._refresh_requested[varname] -= 1
                raise AssertionError
            return False
        except (AssertionError, KeyError):
            if varname.startswith('_status'):
                self._logger.debug('Setting %s for %s to %s' %
                                   (varname, self._instancename, value))
            self._properties[varname] = value
            self._queue_to_frontend.put_nowait((varname, value))
            return True
        finally:
            # set the timestamp
            self._timestamps[varname] = time.time()

    def _log(self):
        """Write a line in the log-file, according to `self.log_formatstr`.
        """
        if (not self.logfile) or (not self.log_formatstr):
            return
        with open(self.logfile, 'a+', encoding='utf-8') as f:
            try:
                f.write(
                    ('%.3f\t' % time.time()) + self.log_formatstr.format(**self._properties) + '\n')
            except KeyError as ke:
                if not self._juststarted:
                    self._logger.warn('KeyError while producing log line for device %s. Missing key: %s' % (
                        self._instancename, ke.args[0]))

    def _idle_worker(self):
        """This function, called as an idle procedure, queries the queue for results from the 
        back-end and emits the corresponding signals."""
        while True:
            try:
                propertyname, newvalue = self._queue_to_frontend.get_nowait()
                if (propertyname=='_dead'):
                    # backend process died.
                    self._logger.error(
                        'Communication error in device %s, disconnecting.' % self._instancename)
                    # disconnect from the device, attempt to reconnect to it.
                    self.disconnect_device(because_of_failure=True)
                    self.emit('error', '', newvalue[0], newvalue[1])
                elif (propertyname == '_startup_done'):
                    self.emit('startupdone')
                elif (propertyname == '_telemetry'):
                    self.emit('telemetry', newvalue)
                elif (propertyname == '_watchdog'):
                    if self._ready:
                        self._logger.warning('Watchdog timeout in device %s: restarting background process.' % self.name)
                        self._stop_background_process()
                        self._start_background_process()
                    else:
                        self._stop_background_process()
                        self.disconnect_device(True)
                elif (propertyname == '_log'):
                    if newvalue.levelno >= logging.getLogger(__name__).getEffectiveLevel():
                        self._logger.handle(newvalue)
                elif isinstance(newvalue, tuple) and isinstance(newvalue[0], Exception):
                    self.emit('error', propertyname, newvalue[0], newvalue[1])
                else:
                    self._properties[propertyname] = newvalue
                    self._timestamps[propertyname] = time.time()
                    self.emit('variable-change', propertyname, newvalue)
            except queue.Empty:
                break
        return True  # this is an idle function, we want to be called again.

    def do_error(self, propertyname, exception, tb):
        self._logger.error(
            'Device error. Variable name: %s. Exception: %s. Traceback: %s' % (propertyname, str(exception), tb))

    def do_startupdone(self):
        self._ready=True
        self._logger.info('Device %s is ready.' % self._instancename)
        return False

    def do_disconnect(self, because_of_failure):
        self._logger.warning('Disconnecting from device %s. Failure flag: %s' % (
            self._instancename, because_of_failure))
        if self._properties['_status'] != 'Disconnected':
            self._properties['_status'] = 'Disconnected'
            self.emit('variable-change', '_status', 'Disconnected')
        return False

    def do_telemetry(self, telemetry):
        self._outstanding_telemetry = False

    def _get_connected(self):
        """Check if we have a connection to the device. You should not call
        this directly."""
        raise NotImplementedError

    def connect_device(self, *args):
        """Connect to the device. This consists of the following steps:
        1) ensuring a sane environment: the connection is not yet established
        and the background process is not running.
        2) establish tcp, modbus, serial, whatever connection.
        3) call _initialize_after_connect
        4) start the background process.

        Before step 4), the front-end owns the connection variables (socket,
        file handle, etc.), which should be instance variables. In step 4,
        the background process takes full ownership of these: i.e. the front
        end must not touch them.

        If you want to do something just after the background process started,
        push the appropriate messages into `_queue_to_background` in step 3).

        Connection and communication parameters (e.g. host, port, baud rate,
        timeout etc.) should be given as arguments to this method. These have
        also to be saved somewhere, where the `reconnect_device()` method can
        find it. Preferably in the instance attribute `_connection_parameters`,
        the implementation of which depends on the subclass.

        If an exception happens at any step, the state of the device has to be
        returned to disconnected. If the exception happens in 4), 
        _finalize_after_disconnect() has to be called.
        """
        raise NotImplementedError

    def disconnect_device(self, because_of_failure=False):
        """Disconnect from the device. This consists of the following steps:
        1) ensure that the environment is sane: the connection is established
        2) stop (and wait for) the background process
        3) run _finalize_after_disconnect
        4) close socket/modbus/whatever
        5) emit 'disconnect' signal

        Note that disconnecting can be unexpected, i.e. due to a communications
        failure or because of the remote end. In this case this function is
        called on a queue message from the backend.
        """
        raise NotImplementedError

    def reconnect_device(self):
        """Try to reconnect the device after a spontaneous disconnection.
        This method must simply call the `connect_device` method, with
        the connection parameters stored by a previous invocation of the
        latter."""
        raise NotImplementedError

    def _initialize_after_connect(self):
        """Do initialization after the connection has been established to the
        device"""
        pass

    def _finalize_after_disconnect(self):
        """Do finalization after the connection to the device has been broken down.
        """
        pass

    def _query_variable(self, variablename):
        """Queries the value of the current variable.

        If `variablename` is None, query ALL known variables.

        This method runs in the background process. Must block until the new value has been
        obtained from the device.
        """
        raise NotImplementedError

    def _set_variable(self, variable, value):
        """Does the actual job of setting a device variable by contacting the device. Must
        block until acknowledgement is obtained from the device. Run from the background
        process"""
        raise NotImplementedError

    def _execute_command(self, commandname, arguments):
        """Does the actual job of executing the command by contacting the device. Run from
        the background process. 
        """
        raise NotImplementedError

    def _process_incoming_message(self, message):
        """This is run if a message arrives from the device."""
        raise NotImplementedError


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

    def _on_start_backgroundprocess(self):
        self._flushoutqueue()
        return Device._on_start_backgroundprocess(self)

    def connect_device(self, host, port, socket_timeout, poll_timeout):
        self._logger.debug('Connecting to device: %s:%d' % (host, port))
        if self._get_connected():
            raise DeviceError('Already connected')
        self._connection_parameters = (host, port, socket_timeout, poll_timeout)
        try:
            self._tcpsocket = socket.create_connection(
                (host, port), socket_timeout)
            self._tcpsocket.setblocking(False)
            self._poll_timeout = poll_timeout
        except (socket.error, socket.gaierror, socket.herror, ConnectionRefusedError) as exc:
            self._logger.error(
                'Error initializing socket connection to device %s:%d' % (host, port))
            raise DeviceError('Cannot connect to device.',exc)
        self._communication_subprocess = multiprocessing.Process(
            target=self._communication_worker)
        self._communication_subprocess.daemon=True
        self._communication_subprocess.start()
        self._logger.debug(
            'Communication subprocess started for device %s:%d' % (host, port))
        try:
            self._start_background_process()
        except Exception as exc:
            self._outqueue.put_nowait(('exit', None))
            try:
                self._communication_subprocess.join()
            except AssertionError:
                pass
            del self._communication_subprocess
            self._tcpsocket.shutdown(socket.SHUT_RDWR)
            self._tcpsocket.close()
            del self._tcpsocket
            raise exc
        try:
            self._initialize_after_connect()
        except Exception as exc:
            self._stop_background_process()
            self._outqueue.put_nowait(('exit', None))
            try:
                self._communication_subprocess.join()
            except AssertionError:
                pass
            del self._communication_subprocess
            self._tcpsocket.shutdown(socket.SHUT_RDWR)
            self._tcpsocket.close()
            del self._tcpsocket
            raise exc
        self._logger.debug('Connected to device %s:%d' % (host, port))

    def disconnect_device(self, because_of_failure=False):
        if not self._get_connected():
            raise DeviceError('Not connected')
        self._logger.debug('Disconnecting from device%s' %
                           (['', ' because of a failure'][because_of_failure]))
        try:
            self._stop_background_process()
            self._logger.debug('Stopped background process')
            try:
                self._finalize_after_disconnect()
                self._logger.debug('Finalized')
            except Exception as exc:
                logger.error('Error while finalizing %s after disconnect: %s %s'%(self._instancename,exc,traceback.format_exc()))
            self._outqueue.put_nowait(('exit', None))
            try:
                self._communication_subprocess.join()
            except AssertionError:
                pass
            self._logger.debug('Closed communication subprocess')
            try:
                self._tcpsocket.shutdown(socket.SHUT_RDWR)
                self._tcpsocket.close()
            except OSError:
                pass
            self._logger.debug('Closed socket')
        finally:
            del self._communication_subprocess
            del self._tcpsocket
            self.emit('disconnect', because_of_failure)

    def reconnect_device(self):
        self.connect_device(*self._connection_parameters)

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
                self._queue_to_backend.put_nowait(('incoming', None, message))
        except CommunicationError as exc:
            self._queue_to_backend.put_nowait(
                ('communication_error', exc, traceback.format_exc()))
        except Exception as exc:
            try:
                raise CommunicationError(exc)
            except CommunicationError as exc:
                self._queue_to_backend.put_nowait(('communication_error',exc,traceback.format_exc()))
        finally:
            polling.unregister(self._tcpsocket)


class Device_ModbusTCP(Device):
    """Device with Modbus over TCP connection.
    """

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)

    def _get_connected(self):
        """Check if we have a connection to the device. You should not call
        this directly."""
        return hasattr(self, '_modbusclient')

    def connect_device(self, host, port, modbus_timeout):
        self._logger.debug('Connecting to device: %s:%d' % (host, port))
        if self._get_connected():
            raise DeviceError('Already connected')
        self._connection_parameters = (host, port, modbus_timeout)
        self._modbusclient = ModbusClient(host, port, timeout=modbus_timeout)
        if not self._modbusclient.open():
            raise DeviceError(
                'Error initializing Modbus over TCP connection to device %s:%d' % (host, port))
        try:
            self._initialize_after_connect()
            try:
                self._start_background_process()
            except Exception as exc:
                self._finalize_after_disconnect()
                raise exc
        except Exception as exc:
            self._modbusclient.close()
            del self._modbusclient
            raise exc
        self._logger.debug('Connected to device %s:%d' % (host, port))

    def disconnect_device(self, because_of_failure=False):
        if not self._get_connected():
            raise DeviceError('Not connected')
        self._logger.debug('Disconnecting from device %s:%d%s' % (
            self._modbusclient.host(), self._modbusclient.port(), ['', ' because of a failure'][because_of_failure]))
        try:
            self._stop_background_process()
            self._logger.debug('Stopped background process')
            self._finalize_after_disconnect()
            self._logger.debug('Finalized')
            self._modbusclient.close()
            self._logger.debug('Closed socket')
        finally:
            del self._modbusclient
            self.emit('disconnect', because_of_failure)

    def reconnect_device(self):
        self.connect_device(*self._connection_parameters)

    def _read_integer(self, regno):
        result = self._modbusclient.read_holding_registers(regno, 1)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error reading integer from register #%d' % regno)
        return result[0]


    def _write_coil(self, coilno, val):
        if self._modbusclient.write_single_coil(coilno, val) is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error writing %s to coil #%d' % (val, coilno))

    def _read_coils(self, coilstart, coilnum):
        result = self._modbusclient.read_coils(coilstart, coilnum)
        if result is None:
            if not self._modbusclient.is_open():
                raise CommunicationError('Error reading coils #%d - #%d' % (coilstart, coilstart + coilnum))
        return result
