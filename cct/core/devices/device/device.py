import logging
import multiprocessing
import os
import queue
import resource
import sys
import time
import traceback
from logging.handlers import QueueHandler

from gi.repository import GLib, GObject

from .exceptions import DeviceError, CommunicationError, WatchdogTimeout

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class QueueLogHandler(QueueHandler):
    def prepare(self, record):
        return {'type':'log', 'logrecord':record,'timestamp':time.monotonic(),'id':0}

class Device(GObject.GObject):
    """The abstract base class of a device, i.e. a component of the SAXS
    instrument, such as an X-ray source, a motor controller or a detector.

    The interface to a device consists of two parts: the first one runs in
    the front-end process, i.e. that of running the GUI. The other one is a
    background process, which takes care of the communication with the
    hardware.

    Properties (such as high voltage, shutter state for an X-ray source)
    are stored in the dictionary `self._properties`. Higher level parts of
    this program may access device properties only through `self.get_variable()`
    and `self.set_variable()`. Property names beginning with underscores ('_')
    are reserved for internal use.

    A refresh of a property can be initiated by calling `self.refresh_variable()`.

    Under the hood, two queues are maintained for communication between the
    front-end and back-end processes for passing information.

    Messages are dictionaries, with the following required fields:
    'type': the message type
    'id': an integral message ID
    'timestamp': a timestamp from time.monotonic()

    Supported message types from the frontend to the backend:
        'query': query a variable. Additional fields:
            'name': the name of the variable
            'signal_needed': if an 'update' message is requested from the
                background thread even if the value is unchanged. This should
                be typically True, but some marginal cases a False value is
                more appropriate.
        'set': set a variable. Additional fields:
            'name': the name of the variable
            'value': the new value of the variable
        'execute': execute a command on the instrument. Additional fields:
            'name': the name of the command.
            'arguments': the arguments for the command as a tuple.
        'exit': end the background process
        'telemetry': request telemetry
        'config': an update of the config dictionary is sent. Fields:
            'configdict': the updated config dictionary

    Other supported message types to the backend, from the communication facilities:
        'incoming': an incoming message. Additional fields:
            'message': the message, typically an instance of `bytes`
        'communication_error': fatal communication error happened.
            'exception': the exception instance
            'traceback': the traceback

    Message types from the backend to the frontend:
        'update': a variable has been updated. Additional fields:
            'name': the name of the variable
            'value': the new value of the variable
        'telemetry': telemetry data. Additional fields:
            'data': the telemetry data
        'error': a non-critical error happened
            'variablename': if the error can be tied to a variable, this is its
                name. Otherwise it should be None
            'exception': the exception instance
            'traceback': the traceback, not a traceback object, but a string,
                since traceback instances are not pickleable.
        'exited': signifies that the background process exited. This is the
            last message the background process sends over the queue to the
            front-end. Fields:
            'normaltermination': False if it terminated unexpectedly.
        'log': message to be logged via the Python log facility.
            'logrecord': a full-fledged log record.
        'ready': sent only once, when the instrument became ready, i.e. all
            variables have been read at least once, and all initialization
            tasks have been completed.

    Properties are refreshed periodically, automatically by the background
    process. The period is in `self.backend_interval`. If during such a refresh
    a change in the value occurs, the back-end sends an 'update' message
    through `_queue_to_frontend`. If no change occurred, an 'update' message
    is only sent if the frontend requested an update with a previous 'query'
    message.

    On the front-end side, an idle function is running, which takes care of
    reading `_queue_to_frontend` and emit-ing variable-change signals.

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

        # emitted on (normal or abnormal) disconnect. The boolean argument is True if the
        # disconnection was abnormal
        'disconnect': (GObject.SignalFlags.RUN_LAST, None, (bool,)),

        # emitted when the starup is done, i.e. all variables have been read at
        # least once
        'startupdone': (GObject.SignalFlags.RUN_FIRST, None, ()),

        # emitted when a response for a telemetry request has been received.
        # The argument is a dict.
        'telemetry': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    # List containing the names of all variables defined for this instrument
    _all_variables=None

    # A minimal list of variable names, which, when queried, result in the
    # updating of all the variables in __all_variables__
    _minimum_query_variables=None

    backend_interval = 1

    watchdog_timeout = 10

    log_formatstr = None

    reply_timeout = 5

    # A dict of outstanding variable queries. Whenever a variable query is
    # requested (either from the front-end thread or by an automatic "idle"
    # query), a key in this dict with the variable name is inserted in this
    # dict, the corresponding value being the actual value of time.monotonic().
    # Whenever a value for the variable is obtained from the device, the key
    # should be deleted from this dict. If a subsequent query of this variable
    # is issued, while there is still an outstanding (not yet executed) query,
    # it is quietly dropped, i.e. no communication is initiated with the device.
    # However, if the timestamp is older than a given age (specified in seconds
    # in `_query_timeout`), the timestamp is re-set.
    _query_requested=None

    # Timeout for re-query, see `_query_requested`.
    _query_timeout=10

    def __init__(self, instancename, logdir='log', configdir='config', configdict=None):
        GObject.GObject.__init__(self)
        self._msgidcounter=0
        # the folder where config files are stored.
        self.configdir = configdir
        # this is the parameter logfile. Note that this is another kind of logging, not related to the logging module.
        self.logfile = os.path.join(logdir, instancename + '.log')
        # some devices keep a copy of the configuration dictionary
        if configdict is not None:
            self.config = configdict
        else:
            self.config = {}
        # the name of this instance, usually a name of the device, like pilatus300k, tmcm351a, etc.
        self._instancename = instancename
        # True if a telemetry request has not yet been processed. If another telemetry request arrives, it will be skipped.
        self._outstanding_telemetry = False
        # The property dictionary
        self._properties = {'_status': 'Disconnected', '_auxstatus':None}
        # Timestamp dictionary, containing the times of the last update
        self._timestamps = {'_status': time.time(), '_auxstatus':time.time()}
        # Queue for messages sent to the backend. Multiple processes might use it, but only the backend should read it.
        self._queue_to_backend = multiprocessing.Queue()
        # Queue for the frontend. Only the backend process should write it, and only the frontend should read it.
        self._queue_to_frontend = multiprocessing.Queue()
        # A dictionary with the names of the parameters which are required to be re-queried. The keys are the parameter
        # names, and the values are integers: how many times the refresh has been requested.
        self._refresh_requested = {}
        # How many times the background thread has been started up.
        self._background_startup_count=0
        # This is True when a connection to the device has been established AND the device has been initialized AND the
        # values of all parameters have been obtained.
        self._ready=False
        # the backend process must be started only after the connection to the device
        # has been established.
        self._loglevel=logger.level

    @property
    def name(self):
        return self._instancename

    def _send_to_backend(self, msgtype, **kwargs):
        """Send a message to the backend process.

        msgtype: the type of the message

        The common required fields (id, timestamp) are computed automatically.
        Give all the other required fields as keyword arguments.
        """
        self._msgidcounter+=1
        msg={'type':msgtype,
             'id':self._msgidcounter,
             'timestamp':time.monotonic()}
        msg.update(kwargs)
        self._queue_to_backend.put(msg)

    def _send_to_frontend(self, msgtype, **kwargs):
        """BACKGROUND_PROCESS:

        Send a message to the frontend process.

        msgtype: the type of the message

        The common required fields (id, timestamp) are computed automatically.
        Give all the other required fields as keyword arguments.
        """
        self._msgidcounter+=1
        msg={'type':msgtype,
             'id':self._msgidcounter,
             'timestamp':time.monotonic()}
        msg.update(kwargs)
        self._queue_to_frontend.put(msg)

    def send_config(self, configdict):
        """Update the config dictionary in the main process and the backend as well."""
        self.config = configdict
        self._send_to_backend('config',configdict=configdict)

    def _load_state(self, dictionary):
        """Load the state of this device to a dictionary. You probably need to
        override this method in subclasses. Do not forget to call the parent's
        method, though."""
        self.log_formatstr = dictionary['log_formatstr']
        self.backend_interval = dictionary['backend_interval']

    def _save_state(self):
        """Write the state of this device to a dictionary and return it for
        subsequent saving to a file. You probably need to override this method
        in subclasses. Do not forget to call the parent's method, though."""
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
            target=self._background_worker, daemon=True,
            name=self.name+'_background', args=(self._background_startup_count,
                                                self._loglevel))
        self._background_process.start()
        self._idle_handler = GLib.idle_add(self._idle_worker)
        logger.debug('Background process for %s has been started' %self.name)

    def _stop_background_process(self):
        """Stops the background process."""
        if hasattr(self,'_background_process'):
            self._send_to_backend('exit')

    def get_variable(self, name):
        """Get the value of the variable. If you need the most fresh value,
        connect to 'variable-change' and call `self.refresh_variable()`.
        """
        return self._properties[name]

    def set_variable(self, name, value):
        """Set the value of the variable. In order to ensure that the variable
        has really been updated, connect to 'variable-change' before calling
        this."""
        self._send_to_backend('set',name=name,value=value)
        self.refresh_variable(name)

    def list_variables(self):
        """Return the names of all currently defined properties as a list"""
        return list(self._properties.keys())

    def is_background_process_alive(self):
        """Checks if the background process is alive"""
        try:
            return self._background_process.is_alive()
        except AttributeError:
            return False

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
        if (not check_backend_alive) or self.is_background_process_alive():
            self._send_to_backend('query',name=name, signal_needed=signal_needed)
        else:
            raise DeviceError('Backend process not running.')

    def execute_command(self, command, *args):
        """Initiate the execution of a command on the device.

        The arguments are device dependent. End-users typically do not need to
        call this method: in a typical subclass concrete methods should be
        implemented for each command.

        Typical usage cases include starting or stopping an exposure,
        opening/closing the beam shutter or moving a motor.

        This function returns before the completion (and probably the start)
        of the command. Command completion can be signalled by the backend
        via changes in parameters (using 'update' messages)
        """
        self._send_to_backend('execute',name=command,arguments=args)

    def _suppress_watchdog(self):
        """BACKGROUND_PROCESS:

        Suppresses checking for device inactivity. Some devices can
        become intentionally inactive for a long time, e.g. Pilatus
        when exposing multiple frames."""
        self._watchdog_alive = False

    def _release_watchdog(self):
        """BACKGROUND_PROCESS:

        Resumes checking for device inactivity"""
        self._watchdogtime = time.time()
        self._watchdog_alive = True

    def _on_background_queue_empty(self):
        """BACKGROUND_PROCESS:

        Do housekeeping tasks when the input queue is empty.
        """
        if (not self._ready) and (self._has_all_variables()):
            #self._logger.debug('Device %s became ready.\n'%self.name + 'Variables:\n\t'+'\n\t'.join([k+' = '+str(self._properties[k]) for k in sorted(self._properties)]))
            self._on_startupdone()
            self._ready=True
            self._send_to_frontend('ready')
        self._check_watchdog()
        self._query_variable(None) # query all variables
        self._log()

    def _on_start_backgroundprocess(self):
        """BACKGROUND_PROCESS:

        Called just before the infinite loop of the background process starts."""
        self._update_variable('_status','Initializing')

    def _background_worker(self, startup_number, loglevel):
        """Worker function of the background thread. The main job of this is
        to run periodic checks on the hardware (polling) and updating 
        `self._properties` accordingly, as well as writing log files.

        The communication between the front-end and back-end is only through
        `self._queue_to_backend` and `self._queue_to_frontend`. Note that
        each process has a different copy of `self._properties`, thus we
        cannot use it for communication. See the details in the class-level
        docstring.

        This method should not be overloaded. The actual
        work is delegated to `_set_variable()`, `_execute_command()` and
        `_query_variable()`, which should be overridden case-by-case.

        In some cases a separate process is responsible for communication
        with the device. Upon an incoming message, that process should also
        use `self._queue_to_backend`, in order to send the message to this
        backend process. The method `self._process_incoming_message` is called
        every time a new message comes. It is responsible to call
        `self._update_variable`.
        """
        self._ready=False
        self._last_queryall=0
        self._lastquerytime=0
        self._lastsendtime=0
        self._lastrecvtime=0
        self._query_requested={} # re-initialize this dict.
        self._background_startup_count=startup_number
        self._count_queries=0
        self._count_inmessages=0
        self._count_outmessages=0
        self._logger = logging.getLogger(
            __name__ + '::' + self.name + '__backgroundprocess')
        self._logger.propagate = False
        if not self._logger.hasHandlers():
            self._logger.addHandler(QueueLogHandler(self._queue_to_frontend))
            self._logger.addHandler(logging.StreamHandler())
        self._logger.setLevel(loglevel)
        # empty the properties dictionary
        self._properties = {}
        self._on_start_backgroundprocess()
        self._pat_watchdog()
        self._release_watchdog()
        self._logger.info(
            'Background thread started for %s, this is startup #%d'%(
                self.name, self._background_startup_count))
        exit_status=False # abnormal termination
        while True:
            try:
                try:
                    message = self._queue_to_backend.get(
                        block=True, timeout=self.backend_interval)
                except queue.Empty:
                    pass
                else:
                    # if no message was pending, a queue.Empty exception has
                    # already been raised at this point.
                    if message['type'] == 'config':
                        self.config = message['configdict']
                    elif message['type'] == 'telemetry':
                        tm = self._get_telemetry()
                        self._send_to_frontend('telemetry',data=tm)
                    elif message['type'] == 'exit':
                        exit_status=True # normal termination
                        break  # the while True loop
                    elif message['type'] == 'query':
                        if message['signal_needed']:
                            try:
                                self._refresh_requested[message['name']] +=1
                            except KeyError:
                                self._refresh_requested[message['name']] = 1
                        self._lastquerytime=time.monotonic()
                        self._query_variable(message['name'])
                    elif message['type'] == 'set':
                        # the following command can raise a ReadOnlyVariable exception
                        self._set_variable(message['name'], message['value'])
                    elif message['type'] == 'execute':
                        self._execute_command(message['name'], message['arguments'])
                    elif message['type'] == 'communication_error':
                        raise message['exception']
                    elif message['type'] == 'incoming':
                        self._lastrecvtime=message['timestamp']
                        self._count_inmessages+=1
                        self._process_incoming_message(message=message['message'],
                                                       original_sent=message['sent'])
                    elif message['type'] == 'log':
                        self._queue_to_frontend.put_nowait(message)
                    elif message['type'] == 'send_complete':
                        # sending of a message finished.
                        self._lastsendtime=message['timestamp']
                    else:
                        raise NotImplementedError(
                            'Unknown command for _background_worker: %s' % message['type'])
                # call the housekeeping tasks
                self._on_background_queue_empty()
            except CommunicationError as ce:
                self._logger.error(
                    'Communication error for device %s, exiting background process.'%(
                        self.name))
                self._send_to_frontend('error',variablename=None, exception=ce, traceback=str(sys.exc_info()[2]))
                exit_status=False # abnormal termination
                break
            except WatchdogTimeout as wt:
                self._logger.error('Watchdog timeout for device %s, exiting loop.'%
                                   self.name)
                break
            except DeviceError as de:
                self._logger.error('DeviceError in the background process for %s: %s'%(
                    self.name, traceback.format_exc()))
                self._send_to_frontend('error', variablename=None, exception=de, traceback=str(sys.exc_info()[2]))
            except Exception as ex:
                self._logger.error('Exception in the background process for %s, exiting. %s'%(
                    self.name, traceback.format_exc()))
                self._send_to_frontend('error',variablename=None, exception=ex, traceback=str(sys.exc_info()[2]))
                exit_status=False # abnormal termination
                break
        self._logger.info('Background process ending for %s. Messages sent: %d.\
Messages received: %d.' % (self.name, self._count_outmessages, self._count_inmessages))
        self._send_to_frontend('exited', normaltermination=exit_status)

    def _get_telemetry(self):
        """BACKGROUND_PROCESS:

        get telemetry data."""
        return {'processname': multiprocessing.current_process().name,
                'self': resource.getrusage(resource.RUSAGE_SELF),
                'children': resource.getrusage(resource.RUSAGE_CHILDREN),
                'inqueuelen': self._queue_to_backend.qsize(),
                'outqueuelen': self._queue_to_frontend.qsize(),
                'last_queryall':time.monotonic()-self._last_queryall,
                'last_recv':time.monotonic()-self._lastrecvtime,
                'last_query':time.monotonic()-self._lastquerytime,
                'last_send':time.monotonic()-self._lastsendtime,
                'watchdog':time.monotonic()-self._watchdogtime,
                'missing_variables':', '.join([v for v in self._all_variables if v not in self._properties])}

    def get_telemetry(self):
        """Request telemetry data from the background process."""
        if not self.is_background_process_alive():
            raise DeviceError('Background process not running, no telemetry.')
        if not self._outstanding_telemetry:
            self._send_to_backend('telemetry')
        else:
            raise DeviceError('Another telemetry request is pending.')

    def _has_all_variables(self):
        """Checks if all the variables have been requested and received at least once.
        The default implementation compares the keys in _properties to those in
        _all_variables."""
        missing=[k for k in self._all_variables if k not in self._properties]
        return not bool(missing)

    def _on_startupdone(self):
        """BACKGROUND_PROCESS:

        Called from the backend thread when the startup is done, i.e. all variables
        have been read."""
        return True

    def _check_watchdog(self):
        """BACKGROUND_PROCESS:

        Check if the connection to the device is alive.
        """
        if ((self._watchdog_alive) and
                ((time.monotonic()-self._watchdogtime)>self.watchdog_timeout)):
            raise WatchdogTimeout

    def _pat_watchdog(self):
        """BACKGROUND_PROCESS:

        "pat" the watchdog: if it does not get patted for a given interval,
        a communication error will be assumed and the connection to the device
        will be torn down and rebuilt.
        """
        self._watchdogtime=time.monotonic()

    def _update_variable(self, varname:str, value:object, force:bool=False) -> bool:
        """BACKGROUND_PROCESS:

        Check if the new value (`value`) of the variable `varname` is different
        from the previous one. If it does, updates the value in `_properties`
        and queues an 'update' message to the frontend. If it does not, but
        `force` is true, it also queues an 'update' message. It also sends an
        'update' message if a refresh of this variable has been requested
        by the frontend process previously. In all cases, we set the timestamp
        for the variable.

        The function returns True if an 'update' message was queued, and False
        otherwise.
        """
        # first of all, pat the watchdog.
        self._pat_watchdog()
        try:
            del self._query_requested[varname]
        except KeyError:
            pass
        try:
            assert(self._properties[varname] == value) # can raise AssertionError and KeyError
            if force:
                raise KeyError
            if varname in self._refresh_requested and self._refresh_requested[varname] > 0:
                self._refresh_requested[varname] -= 1
                raise AssertionError
            return False
        except (AssertionError, KeyError):
#            self._logger.debug('Setting %s for %s to %s' % (varname, self.name, value))
            self._properties[varname] = value
            self._send_to_frontend('update',name=varname,value=value)
            return True
        finally:
            # set the timestamp
            self._timestamps[varname] = time.time()

    def _log(self):
        """BACKGROUND_PROCESS:

        Write a line in the log-file, according to `self.log_formatstr`.
        """
        if (not self.logfile) or (not self.log_formatstr):
            return
        with open(self.logfile, 'a+', encoding='utf-8') as f:
            try:
                f.write(
                    ('%.3f\t' % time.time()) +
                    self.log_formatstr.format(**self._properties) + '\n')
            except KeyError as ke:
                if self._ready:
                    self._logger.warn('KeyError while producing log line for %s: %s' % (
                        self.name, ke.args[0]))

    def _idle_worker(self) -> bool:
        """This function, called as an idle procedure, queries the queue for
        results from the back-end and emits the corresponding signals.

        Each run of this function handles all the pending messages in the queue"""
        while True:
            try:
                message = self._queue_to_frontend.get_nowait()
                if (message['type']=='exited'):
                    if not message['normaltermination']:
                        # backend process died abnormally
                        logger.error(
                            'Communication error in device %s, disconnecting.' % self.name)
                        # disconnect from the device, attempt to reconnect to it.
                    logger.debug('Calling disconnect_device on %s'%self.name)
                    del self._idle_handler
                    logger.debug('Joining background process for %s'%self.name)
                    self._background_process.join()
                    del self._background_process
                    self.disconnect_device(
                        because_of_failure = not message['normaltermination'])
                    logger.debug('Disconnected from device %s'%self.name)

                    return False # prevent re-scheduling this idle handler
                elif (message['type']== 'ready'):
                    self.emit('startupdone')
                elif (message['type'] == 'telemetry'):
                    self.emit('telemetry', message['data'])
                elif (message['type'] == 'log'):
                    if (message['logrecord'].levelno >=
                            logging.getLogger(__name__).getEffectiveLevel()):
                        logger.handle(message['logrecord'])
                elif message['type'] == 'error':
                    self.emit('error', message['variablename'],
                              message['exception'], message['traceback'])
                elif message['type'] == 'update':
                    self._properties[message['name']] = message['value']
                    self._timestamps[message['name']] = time.time()
                    self.emit('variable-change', message['name'], message['value'])
                else:
                    raise NotImplementedError(message['type'])
            except queue.Empty:
                break
        return True  # this is an idle function, we want to be called again.

    def do_error(self, propertyname:str, exception:Exception, tb) -> bool:
        logger.error(
            'Device error. Variable name: %s. Exception: %s. Traceback: %s' % (propertyname, str(exception), tb))

    def do_startupdone(self) -> bool:
        self._ready=True
        logger.info('Device %s is ready.' % self.name)
        return False

    @property
    def ready(self) -> bool:
        return self._ready

    def do_disconnect(self, because_of_failure:bool):
        logger.warning('Disconnecting from device %s. Failure flag: %s' % (
            self.name, because_of_failure))
        if self._properties['_status'] != 'Disconnected':
            self._properties['_status'] = 'Disconnected'
            self.emit('variable-change', '_status', 'Disconnected')
        return False

    def do_telemetry(self, telemetry):
        """Executed when the "telemetry" signal is emitted."""
        self._outstanding_telemetry = False

    def _get_connected(self) -> bool:
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
        #logger.debug('Connecting to device %s'%self.name)
        if self._get_connected():
            raise DeviceError('Already connected')
        self._connection_parameters=args
        # We don't supply arguments directly to the next function, it takes
        # them from `self._connection_parameters`
        self._establish_connection()
        try:
            self._start_background_process()
        except:
            self._breakdown_connection()
            raise
        try:
            self._initialize_after_connect()
        except:
            self._stop_background_process()
            self._breakdown_connection()
            raise
        logger.info('Connected to device %s'%self.name)
        return

    def _establish_connection(self):
        """Establish the connection to the device.

        Abstract method: override this in subclasses.

        Must raise CommunicationError if the connection fails.

        The arguments (e.g. host, port, etc.) to be used are stored by
        `connect_device()` in `self._connection_parameters`

        This method can safely assume that no connection to the device
        exists.
        """
        raise NotImplementedError

    def _breakdown_connection(self):
        """Break down the connection to the devie.

        Abstract method: override this in subclasses.

        Should not raise an exception.

        This method can safely assume that a connection exists to the
        device.
        """
        raise NotImplementedError

    def disconnect_device(self, because_of_failure:bool=False):
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
        if not self._get_connected():
            raise DeviceError('Not connected')
        logger.debug('Disconnecting from device%s' %
                           (['', ' because of a failure'][because_of_failure]))
        try:
            self._stop_background_process()
            logger.debug('Stopped background process')
            self._breakdown_connection()
            logger.debug('Connection broken down.')
            self._finalize_after_disconnect()
            logger.debug('Finalized')
        finally:
            self.emit('disconnect', because_of_failure)

    def reconnect_device(self):
        """Try to reconnect the device after a spontaneous disconnection."""
        return self.connect_device(*(self._connection_parameters))

    def _initialize_after_connect(self):
        """Do initialization after the connection has been established to the
        device"""
        pass

    def _finalize_after_disconnect(self):
        """Do finalization after the connection to the device has been broken down.
        """
        pass

    def _query_variable(self, variablename: object, minimum_query_variables: object = None) -> object:
        """BACKGROUND_PROCESS:

        Queries the value of the current variable. This should typically be
        overridden in derivative classes, but with care (see below).

        If `variablename` is None, query ALL known variables.

        Notes:

        1) some devices, e.g. the pilatus300k can become unresponsive when doing
        work (exposing multiple images). In these cases, this function must
        refrain from the actual querying, even if `variablename` is None.

        2) some devices use blocking connections, i.e. a query gives results
        immediately. In this case, this function is responsible to call
        `_update_variable`. Other devices are asynchronous, i.e. a query command
        has to be sent, to which the device will reply in turn. In this case, the
        reply will come in a form of an 'incoming' message to `_queue_to_background`,
        and `_update_variable` will be called from the `_process_incoming_message`
        method.

        The default implementation of this method enables smart querying:

        1) If the `variablename` argument is None, this method calls itself again
        with the elements of `minimum_query_variables`, finally returning
        False.

        2) If the `variablename` argument is not None, it checks that it is
        present as a key in `self._query_requested`, and if it is, then it
        also checks if the timestamp in the value is not older than
        `self._query_timeout`. If both of these are true, this function returns
        False, Otherwise we return True.

        An overridden method in a derived class typically would call its
        ancestor's method, and only if it returns True, it must start taking
        steps to contact the device for a new value.

        Note that if for some reason you cannot start the query of this variable,
        you should take care to remove the corresponding key from
        `self._query_requested`.

        Whenever an update to this variable arrives from the device, the default
        `self._update_variable` clears the key from `self._query_requested`, if
        present.

        If the argument `minimum_query_variables` is None,
        `self._minimum_query_variables` is used instead of it.
        :type variablename: object
        """
        if variablename is None:
            # query all variables
            if (time.monotonic()-self._last_queryall)<self.backend_interval:
                return False
            self._last_queryall=time.monotonic()
            if minimum_query_variables is None:
                minimum_query_variables=self._minimum_query_variables
            for vn in minimum_query_variables:
                self._query_variable(vn)
                #self._logger.debug('Queried variable %s for %s'%(vn,self.name))
            return False
        try:
            if (self._query_requested[variablename]-time.monotonic())<self._query_timeout:
                return False
            raise KeyError(variablename)
        except KeyError as ke:
            self._query_requested[variablename]=time.monotonic()
            self._lastquerytime=time.monotonic()
            return True

    def _set_variable(self, variable:str, value:object):
        """BACKGROUND_PROCESS:

        Does the actual job of setting a device variable by contacting
        the device.

        First it checks if the variable is writable. If not, a
        ReadOnlyVariable exception is raised.

        Then the validity of the value is checked, possibly taking into account
        the values of already present variables from `self._properties`. If
        invalid, an InvalidValue exception must be raised.

        This method must ensure that an 'update' message is sent to the
        front-end after setting the variable. In case of synchronous devices,
        this function must update the variable by requesting its value from
        the device and calling `_update_variable`. In case of asynchronous
        devices, a query to the variable needs to be queued.
        """
        raise NotImplementedError

    def _execute_command(self, commandname:str, arguments:tuple):
        """BACKGROUND_PROCESS:

        Does the actual job of executing the command by contacting the
        device. Similar to the `_set_variable` method, it must be ensured
        that the front-end process is notified when the command is finished.
        """
        raise NotImplementedError

    def _process_incoming_message(self, message:bytes, original_sent:bytes=None):
        """BACKGROUND_PROCESS:

        This is run if a message arrives from the device. Must call
        `_update_variable` with the obtained new values.

        The argument `message` is the message as received from the device,
        an instance of `bytes`. The actual subclass of Device, which is
        responsible for the way of communication (TCP, RS232, Modbus, etc.),
        usually ensures that the character string `message` is a single and
        complete message. `original_sent` is the message sent to the device,
        to which `message` is a reply.
        """
        raise NotImplementedError

    def get_all_variables(self):
        return self._properties.copy()


