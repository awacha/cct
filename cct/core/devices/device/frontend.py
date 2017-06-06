import logging
import multiprocessing
import os
import queue
import time
import traceback

from .backend import DeviceBackend
from .exceptions import DeviceError
from .message import Message
from ...utils.callback import Callbacks, SignalFlags
from ...utils.timeout import IdleFunction

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Device(Callbacks):
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
    'source': the string ID of the sender

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
    __signals__ = {
        # emitted if the value of a variable changes. The first argument is the
        # name of the variable, the second is its new value. Note that the
        # emission of this signal occurs BEFORE the new value of the variable
        # is stored. This way signal handlers can access the previous value by
        # calling get_variable().
        'variable-change': (SignalFlags.RUN_FIRST, None, (str, object)),

        # emitted if an error happens. The first argument is the the name of the
        # affected variable or '' if no variable corresponds to this error.
        # The second argument is an exception object. The third one is the
        # formatted traceback.
        'error': (SignalFlags.RUN_LAST, None, (str, object, str)),

        # emitted on (normal or abnormal) disconnect. The boolean argument is True if the
        # disconnection was abnormal
        'disconnect': (SignalFlags.RUN_LAST, None, (bool,)),

        # emitted when the starup is done, i.e. all variables have been read at
        # least once
        'ready': (SignalFlags.RUN_FIRST, None, ()),

        # emitted when a response for a telemetry request has been received.
        # The argument is a dict.
        'telemetry': (SignalFlags.RUN_FIRST, None, (object,)),
    }

    # The class we use to instantiate background threads
    backend_class = DeviceBackend

    # List containing the names of all variables defined for this instrument
    all_variables = None

    # A minimal list of variable names, which, when queried, result in the
    # updating of all the variables in __all_variables__
    minimum_query_variables = None

    # Constant variables: not expected to change (such as hardware version,
    # etc.). They will only be autoqueried once.
    constant_variables = None

    # Urgent variables
    urgent_variables = None

    # Urgency modulus. Not urgent variables, which have already been read at
    # least once, will only be checked at every `urgency_modulo`-eth queryall
    # in the backend process. If zero, only urgent variables are queried every
    # time.
    urgency_modulo = 1

    # How long the backend thread waits on its input queue (seconds)
    backend_interval = 1.0

    # How frequently a queryall is issued by the backend (seconds)
    queryall_interval = 1.0

    # A timeout (seconds) for communication with the devices. If no message is
    # obtained from the device before this time, the connection is considered
    # dead, and sudden disconnection ensues.
    watchdog_timeout = 10

    # A format string for logging, must be parsable by str.format(). All state
    # variables are available for substitution. The actual time will be
    # prepended by the background process
    log_formatstr = None

    # Waiting time before two telemetry data collections (seconds)
    telemetry_interval = 2

    # Timeout for re-query, see `query_requested` in the backend process.
    query_timeout = 10

    # Maximum number the "busy" semaphore can be acquired
    max_busy_level = 1

    # Warn if the length of the frontend queue is larger than this.
    frontendqueue_warn_length = 10

    def __init__(self, instancename, logdir='log', configdir='config', configdict=None):
        Callbacks.__init__(self)
        self._msgidcounter = 0
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
        self.name = instancename
        # The property dictionary
        self._properties = {'_status': 'Disconnected', '_auxstatus': None}
        # Timestamp dictionary, containing the times of the last update
        self._timestamps = {'_status': time.monotonic(), '_auxstatus': time.monotonic()}
        # Queue for messages sent to the backend. Multiple processes might use it, but only the backend should read it.
        self._queue_to_backend = multiprocessing.Queue()
        # Queue for the frontend. Only the backend process should write it, and only the frontend should read it.
        self._queue_to_frontend = multiprocessing.Queue()
        # How many times the background thread has been started up.
        self.background_startup_count = 0
        # This is True when a connection to the device has been established AND the device has been initialized AND the
        # values of all parameters have been obtained.
        self._ready = False
        # the backend process must be started only after the connection to the device
        # has been established.
        if not hasattr(self, 'loglevel'):
            logger.debug('Setting log level for device {} to {}'.format(self.name, logger.level))
            self.loglevel = logger.level
        else:
            logger.debug('Not overriding log level in frontend for device {}'.format(self.name))
        self._background_process = None
        self._idle_handler = None
        self._busy = multiprocessing.BoundedSemaphore(self.max_busy_level)
        self.deviceconnectionparameters = None

    def send_to_backend(self, msgtype, **kwargs):
        """Send a message to the backend process.

        msgtype: the type of the message

        The common required fields (id, timestamp) are computed automatically.
        Give all the other required fields as keyword arguments.
        """
        self._msgidcounter += 1
        msg = Message(msgtype, self._msgidcounter, self.name + '__frontend', **kwargs)
        self._queue_to_backend.put(msg)
        del msg

    def send_config(self, configdict):
        """Update the config dictionary in the main process and the backend as well."""
        self.config = configdict
        self.send_to_backend('config', configdict=configdict)

    def load_state(self, dictionary):
        """Load the state of this device to a dictionary. You probably need to
        override this method in subclasses. Do not forget to call the parent's
        method, though."""
        self.log_formatstr = dictionary['log_formatstr']
        self.backend_interval = dictionary['backend_interval']

    def save_state(self):
        """Write the state of this device to a dictionary and return it for
        subsequent saving to a file. You probably need to override this method
        in subclasses. Do not forget to call the parent's method, though."""
        return {'log_formatstr': self.log_formatstr,
                'backend_interval': self.backend_interval}

    def get_variable(self, name):
        """Get the value of the variable. If you need the most fresh value,
        connect to 'variable-change' and call `self.refresh_variable()`.
        """
        return self._properties[name]

    def get_all_variables(self):
        """Get a dictionary of the present values of all state variables."""
        return self._properties.copy()

    def list_variables(self):
        """Return the names of all currently defined properties as a list"""
        return list(self._properties.keys())

    def missing_variables(self):
        """Return a list of missing variables"""
        return [k for k in self.all_variables if k not in self._properties]

    def set_variable(self, name, value):
        """Set the value of the variable. In order to ensure that the variable
        has really been updated, connect to 'variable-change' before calling
        this."""
        self.send_to_backend('set', name=name, value=value)
        self.refresh_variable(name)

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
        if self.get_connected():
            self.send_to_backend('query', name=name, signal_needed=signal_needed)
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
        if self.get_connected():
            self.send_to_backend('execute', name=command, arguments=args)
        else:
            raise DeviceError('Backend process not running.')

    def _idle_worker(self) -> bool:
        """This function, called as an idle procedure, queries the queue for
        results from the back-end and emits the corresponding signals.

        Each run of this function handles all the pending messages in the queue"""
        try:
            while True:
                try:
                    message = self._queue_to_frontend.get_nowait()
                    assert isinstance(message, Message)
                    if (self._queue_to_frontend.qsize() > self.frontendqueue_warn_length) and self.ready:
                        logger.warning(
                            'Too many messages (exactly {}) are waiting in the front-end queue for device {}.'.format(
                                self._queue_to_frontend.qsize(), self.name))
                except queue.Empty:
                    break
                if message['type'] == 'exited':
                    if not message['normaltermination']:
                        # backend process died abnormally
                        logger.error(
                            'Communication error in device ' + self.name + ', disconnecting.')
                    logger.debug('Joining background process for ' + self.name)
                    self._background_process.join()
                    self._background_process = None
                    # this must be here, since a 'disconnect' signal handler can attempt
                    # to reinitialize the connection, thus after the emission of the signal,
                    # we can expect that self._background_process and self._idle_handler carry
                    # the new handlers.
                    self._idle_handler = None
                    logger.debug('Emitting disconnect signal')
                    self.emit('disconnect', not message['normaltermination'])
                    logger.debug('Exiting the previous idle handler.')
                    return False  # prevent re-scheduling this idle handler
                elif message['type'] == 'ready':
                    self._ready = True
                    self.emit('ready')
                elif message['type'] == 'telemetry':
                    self.emit('telemetry', message['data'])
                elif message['type'] == 'log':
                    logger.handle(message['logrecord'])
                elif message['type'] == 'error':
                    self.emit('error', message['variablename'],
                              message['exception'], message['traceback'])
                elif message['type'] == 'update':
                    try:
                        self.emit('variable-change', message['name'], message['value'])
                    finally:
                        self._properties[message['name']] = message['value']
                        self._timestamps[message['name']] = message['timestamp']
                else:
                    raise ValueError(message['type'])
        except Exception as exc:
            logger.error('Error in the idle function for device {}: {} {}'.format(
                self.name, exc, traceback.format_exc()))
        return True  # this is an idle function, we want to be called again.

    def do_disconnect(self, because_of_failure: bool):
        """default handler for the 'disconnect' signal"""
        if because_of_failure:
            logger.warning('Disconnected from device {} due to a failure.'.format(
                self.name))
        else:
            logger.info('Disconnected from device {}.'.format(self.name))
        if self._properties['_status'] != 'Disconnected':
            self._properties['_status'] = 'Disconnected'
            self._timestamps['_status'] = time.monotonic()
            self.emit('variable-change', '_status', 'Disconnected')
        else:
            return True
        return False

    def do_ready(self) -> bool:
        """default handler for the 'ready' signal"""
        logger.info('Device ' + self.name + ' is ready.')
        return False

    # noinspection PyMethodMayBeStatic
    def do_error(self, propertyname: str, exception: Exception, tb: str) -> bool:
        """default handler for the 'error' signal"""
        logger.error(
            'Device error. Variable name: {}. Exception: {}. Traceback: {}'.format(
                propertyname, str(exception), tb))
        return False

    @property
    def ready(self) -> bool:
        return self._ready

    def is_ready(self) -> bool:
        return self._ready

    def get_connected(self) -> bool:
        """Checks if the background process is alive"""
        try:
            return self._background_process.is_alive()
        except AttributeError:
            return False

    def connect_device(self, *args):
        """Establish connection to the device. This simply means firing up the
        background process, which will take care of the rest."""

        assert (self._idle_handler is None) == (self._background_process is None)
        logger.debug('Connecting to device: {} with arguments: {}'.format(self.name, args))
        self.deviceconnectionparameters = args
        if (self._idle_handler is not None) or (self._background_process is not None):
            raise DeviceError('Background process already running')
        # empty the queues.
        while True:
            try:
                msg = self._queue_to_backend.get_nowait()
                logger.debug('Cleared message from queue_to_backend: {}'.format(msg))
            except queue.Empty:
                break
        logger.debug('queue_to_backend empty.')
        # nevertheless, create a fresh queue instance
        self._queue_to_backend = multiprocessing.Queue()
        while True:
            try:
                msg = self._queue_to_frontend.get_nowait()
                logger.debug('Cleared message from queue_to_frontend: {}'.format(msg))
            except queue.Empty:
                break
        logger.debug('queue_to_frontend empty')
        # nevertheless, create a fresh queue instance
        self._queue_to_frontend = multiprocessing.Queue()
        self._ready = False
        # note that we do not clear the '_properties' and '_timestamps' in
        # order to ensure smooth operation of the instrument between sudden
        # disconnects and automatic reconnections.

        # Create a new 'busy' semaphore.
        self._busy = multiprocessing.BoundedSemaphore(self.max_busy_level)

        assert issubclass(self.backend_class, DeviceBackend)
        self._background_process = multiprocessing.Process(
            target=self.backend_class.create_and_run, name=self.name + '_background',
            args=(self.name, self.configdir, self.config, self.deviceconnectionparameters, self._queue_to_backend,
                  self._queue_to_frontend, self.watchdog_timeout, self.backend_interval, self.query_timeout,
                  self.telemetry_interval, self.queryall_interval, self.all_variables, self.minimum_query_variables,
                  self.constant_variables, self.urgent_variables, self.urgency_modulo, self.background_startup_count,
                  self.loglevel, self.logfile, self.log_formatstr, self.max_busy_level, self._busy),
            kwargs=self._get_kwargs_for_backend(),
        )
        self._background_process.daemon = False
        self.background_startup_count += 1
        self._background_process.start()
        logger.debug('Started background process for device {}'.format(self.name))
        self._idle_handler = IdleFunction(self._idle_worker)
        logger.debug('Started idle handler for device {}'.format(self.name))

    # noinspection PyMethodMayBeStatic
    def _get_kwargs_for_backend(self):
        """You can supply custom keyword arguments to the __init__() method of
        the backend process by overriding this method and returning the desired
        'kwargs' dict."""
        return dict()

    def disconnect_device(self):
        """Initiate disconnection from the device: request the background
        process to stop.

        Just before the background process has finished, it will send us an
        'exited' message through the queue, which 'self._idle_handler' will
        pick up and handle.
        """
        if self._background_process is not None:
            self.send_to_backend('exit')

    def reconnect_device(self):
        """Try to reconnect the device after a spontaneous disconnection."""
        return self.connect_device(*self.deviceconnectionparameters)

    def is_busy(self) -> int:
        """Returns how many times the busy semaphore has been acquired. This
        way, the return value casted to bool makes sense semantically."""
        return self.max_busy_level - self._busy.get_value()
