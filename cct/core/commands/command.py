import logging
import traceback
import weakref
from typing import Dict

from .exceptions import JumpException
from ..devices import Motor
from ..utils.callback import Callbacks, SignalFlags
from ..utils.timeout import TimeOut, IdleFunction

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CommandError(Exception):
    pass


class CommandTimeoutError(CommandError):
    pass


class CommandArgumentError(CommandError):
    pass


class CommandKilledError(CommandError):
    pass


class Command(Callbacks):
    """This is an abstract base class for a command, which can be issued in
    order to do something on the instrument, e.g. move a motor or take an
    exposure.

    The `name` class variable is the command name: this will be used to
    determine which command has to be run from a command line. It must be
    unique among all derived classes.

    The life cycle of a Command instance is as follows:

    1) It is instantiated either directly by Python code, or from a command
    line parsed by the interpreter (cct.core.services.interpreter.Interpreter
    instance). The __init__() method gets the following arguments:
        interpreter: the interpreter instance. The constructor of this abstract
            base class stores a weakref.proxy to it as self.interpreter.
        args: positional command arguments (you probably need them)
        kwargs: command keyword arguments (if you need them)
        namespace: a dictionary containing the variables accessible by the
            command.
    All of these are stored as instance variables of the same name. If you
    subclass Command, __init__() must perform some checks of the validity
    and range of the arguments and the presence or absence of certain
    variables in the namespace.

    2) Very soon after this, the _execute() method is called (note the
    underscore!) by the interpreter. You should not overload this function,
    as it does the following:
        - check the validity of the arguments using self.validate()
        - call self.execute(), which does the actual execution.

    3) self.validate() must return True if the arguments and the environment
    have met the criteria. It must raise an exception (subclass of
    CommandError) if something is wrong. In general, all types of validation
    must be done as soon as possible. E.g. number and type of arguments in
    self.__init__(), and the validity of motor soft limits in self.validate().

    4) self.execute() is called if self.validate() returned True. It must
    _commence_ the execution of the command, but it _must_not_ finish it.
    It must return True if the execution of the command started successfully,
    and raise an instance of CommandError (or of one of its subclasses) if
    something went wrong.

    5) When the command finishes, it must call self.cleanup(), which frees all
    allocated resources and emits the 'return' signal, notifying the
    interpreter that we are done.

    6) If an error happens during execution of the command, the 'fail' signal
    has to be emitted. From this, the interpreter will know that something
    fatal has happened, and if it is in a middle of a script, it must not
    continue. However, the 'return' signal still has to be sent by calling
    self.cleanup().

    7) self.kill() is a mechanism to prematurely stop the execution of the
    command. It must ensure that the instrument is idle and self.cleanup()
    is called as soon as possible, but not before returning from this function.

    The main idea is non-blocking operation: the main process (responsible for
    GUI operations) must never be kept busy too long. As many commands work on
    the instrument and cause changes in state varibles of the devices, the
    preferred way of operation is to install a callback handler to the
    'variable-change' signal of the given devices, and call self.cleanup()
    when the appropriate variable has the appropriate value. To make things
    easier, the class variable `required_devices` can be a list with the
    names of the devices. Valid names are those which can be queried by
    cct.core.instrument.Instrument.get_device(). The method self._execute()
    connects the following signal handlers:
        'variable-change' -> self.on_variable_change
        'error' -> self.on_error
        'disconnect' -> self.disconnect
    You can override these signal handlers. Of course, self.cleanup() takes
    care of disconnecting these.

    If you write a simple command, which does not interact with the instrument
    but takes time (e.g. sleep for a given time), you should install a GLib
    timeout function in self.execute(), which calls self.cleanup() when the
    needed time has elapsed.

    If the command is even more simple, i.e. the result can be determined by
    self.execute(), you should install a GLib idle handler, which calls
    self.cleanup(). For your convenience, self.idle_return() does just this.
    Just call this method with your desired return value. Once again, DO NOT
    CALL self.cleanup() FROM self.execute()!

    As a safety net, you can specify a timeout for a command either in the
    subclass definition or in __init__ by setting self.timeout to a positive
    number. If self.timeout is not None, self._execute() will install a GLib
    timeout handler after self.execute() returns. If self.cleanup() is not
    called before this time elapses, a 'fail' signal is emitted with a
    CommandTimeoutError, before the 'return' signal. This is done by the
    self.on_timeout() method, which you can override if you really need to.

    A similar feature is the `pulse_interval` class variable. If it is not
    None, but a positive number, self._execute() installs a GLib timeout
    handler after self.execute() returns. It will periodically call
    self.on_pulse(), which you can override to do the actual work. Take care
    that returning False from self.on_pulse() will inhibit further calling of
    this method, so always return True if you want to be called again. As you
    would expect, self.cleanup() removes the pulse handler. The most common job
    of the pulse handler is to give feedback to the user that the command is
    running. If you know exactly, how long it would take before finishing,
    consider emitting the 'progress' signal, where you can specify a fraction
    and a text message, to be used in a progress bar. If you do not know the
    exact duration of the command, emit the 'pulse' signal, which will just
    'pulse' the progress bar to and fro, while also presenting a text message.

    Other signals can also be defined in subclasses.

    Once again, as a general rule, signals must not be emitted from
    self.execute() and self.kill() member functions. Use idle functions or
    callbacks for this.
    """
    __signals__ = {
        # emitted when the command completes. Must be emitted exactly once.
        # This also must be the last signal emitted by the command. The single
        # argument is the return value of the command.
        'return': (SignalFlags.RUN_FIRST, None, (object,)),
        # emitted on a failure. Can be emitted multiple times. The first
        # argument is an Exception instance, the second one is the traceback
        # formatted using traceback.format_exc()
        'fail': (SignalFlags.RUN_LAST, None, (object, str)),
        # long running commands where the duration cannot be estimated in
        # advance, should emit this periodically (say in every second). The
        # string argument is a message detailing the current state of the
        # command (what it is doing presently).
        'pulse': (SignalFlags.RUN_FIRST, None, (str,)),
        # long running commands where the duration can be estimated in advance,
        # should emit this signal periodically (e.g. in every second). The
        # first argument is a text message detailing the current state of the
        # command, while the float argument must be a number between 0 and 1,
        # the fraction of the job done up to now. It doesn't need to increase
        # in time. If needed, it can decrease also.
        'progress': (SignalFlags.RUN_FIRST, None, (str, float)),
        # send occasional text messages to the command interpreter, to be
        # written to a terminal or logged at the INFO level.
        'message': (SignalFlags.RUN_FIRST, None, (str,)),
        # can be sent to give the front-end command-dependent details. A
        # typical use case is the transmission command, which uses this
        # mechanism to notify the front-end of what it has currently been
        # doing. The single argument of this signal depends on the command,
        # but typically it should be a dict.
        'detail': (SignalFlags.RUN_FIRST, None, (object,))
    }

    instance_count = 0

    name = '__abstract__'

    required_devices = []

    timeout = None  # seconds

    pulse_interval = None  # seconds

    def __new__(cls, *args, **kwargs):
        cls.instance_count += 1
        obj = super().__new__(cls)
        logger.debug('Instantiating a command. Number of instances including this: {:d}'.format(cls.instance_count))
        return obj

    def __init__(self, interpreter, args, kwargs, namespace):
        super().__init__()
        try:
            self.interpreter = weakref.proxy(interpreter)
        except TypeError:
            if isinstance(interpreter, weakref.ProxyTypes):
                self.interpreter = interpreter
            else:
                raise
        self.args = args
        self.kwargs = kwargs
        self.namespace = namespace
        self._device_connections = {}
        self._timeout_handler = None
        self._pulse_handler = None
        self._returning = False

    def __del__(self):
        self.__class__.instance_count -= 1
        logger.debug('Deleting a command. Number of remaining instances: {:d}'.format(self.__class__.instance_count))

    @property
    def instrument(self):
        return self.interpreter.instrument

    @property
    def services(self):
        return self.interpreter.instrument.services

    @property
    def config(self) -> Dict:
        return self.interpreter.instrument.config

    def get_device(self, name: str):
        return self.interpreter.instrument.get_device(name)

    def get_motor(self, motorname: str) -> Motor:
        return self.interpreter.instrument.motors[motorname]

    def validate(self):
        """Check the validity of self.args and self.kwargs.

        If everything is OK, it should return True. Otherwise
        an appropriate exception, a subclass of CommandError
        should be raised."""
        return True

    def _execute(self):
        self._returning = False
        logger.debug('Executing command {}'.format(self.name))
        if not self.validate():
            logger.error('Validation of command parameters for command {} failed.')
            raise CommandError('Validation of command parameters for command {} failed.'.format(self.name))
        logger.debug('Connecting required devices for command {}'.format(self.name))
        self._connect_devices()
        if self.timeout is not None:
            logger.debug('Starting timeout of {:f} seconds'.format(self.timeout))
            self._timeout_handler = TimeOut(self.timeout * 1000, self.on_timeout)
        if self.pulse_interval is not None:
            logger.debug('Starting pulser of {:f} seconds interval'.format(self.pulse_interval))
            self._pulse_handler = TimeOut(self.pulse_interval * 1000, self.on_pulse)
        try:
            logger.debug('Running execute() method of command {}'.format(self.name))
            retval = self.execute()
        except JumpException as je:
            self.cleanup(None, noemit=True)
            raise
        except Exception as exc:
            logger.error('Error running command {}: {} {}'.format(self.name, str(exc), traceback.format_exc()))
            self.cleanup(None, noemit=True)
            raise
        return retval

    def execute(self):
        """Start the execution of the command."""
        raise NotImplementedError

    def kill(self):
        """Stop running the current command. The default version emits a 'fail'
        signal and cleans up."""
        logger.warning('Killing command {}'.format(self.name))
        try:
            raise CommandKilledError('Command {} killed.'.format(self.name))
        except CommandKilledError as cke:
            self.emit('fail', cke, traceback.format_exc())
        self.idle_return(None)

    def cleanup(self, returnvalue: object = None, noemit=False):
        """Must be called after execution finished."""
        logger.debug('Cleaning up command {}'.format(self.name))
        if self._timeout_handler is not None:
            self._timeout_handler.stop()
            logger.debug('Timeout handler of command {} removed'.format(self.name))
        if self._pulse_handler is not None:
            self._pulse_handler.stop()
            logger.debug('Pulse handler of command {} removed'.format(self.name))
        logger.debug('Disconnecting required devices of command {}'.format(self.name))
        self._disconnect_devices()
        logger.debug('Disconnected required devices of command {}'.format(self.name))
        if not noemit:
            self.emit('return', returnvalue)
        del self.args
        del self.kwargs
        del self.namespace
        del self.interpreter

    def on_timeout(self):
        try:
            raise CommandTimeoutError('Command {} timed out after {:f} seconds'.format(self.name, self.timeout))
        except CommandTimeoutError as exc:
            self.emit('fail', exc, traceback.format_exc())
        self.cleanup(None)

    def on_pulse(self):
        return True

    def _connect_devices(self):
        for d in self.required_devices:
            dev = self.get_device(d)
            self._device_connections[d] = [
                dev.connect('variable-change', self.on_variable_change),
                dev.connect('error', self.on_error),
                dev.connect('disconnect', self.on_disconnect),
            ]
            if isinstance(dev, Motor):
                self._device_connections[d].extend([
                    dev.connect('position-change', self.on_motor_position_change),
                    dev.connect('stop', self.on_motor_stop)
                ])
            logger.debug('Connected required device {} for command {}'.format(d, self.name))

    def _disconnect_devices(self):
        for d in list(self._device_connections.keys()):
            dev = self.get_device(d)
            for c in self._device_connections[d]:
                dev.disconnect(c)
            del self._device_connections[d]
        self._device_connections = {}

    def on_variable_change(self, device, variablename, newvalue):
        return False

    def on_error(self, device, variablename, exc, tb):
        """Emit the 'fail' signal"""
        self.emit('fail', exc, tb)
        return False

    def on_disconnect(self, device, because_of_failure):
        """Emit a fail signal."""
        self.emit('fail', CommandError(
            'Sudden disconnect of device ' + device.name), 'no traceback')
        return False

    def on_motor_position_change(self, motor, newposition):
        return False

    def on_motor_stop(self, motor, targetreached):
        return False

    def idle_return(self, value):
        """Convenience function to schedule an idle function to return."""
        if self._returning:
            return
        self._returning = True
        IdleFunction(lambda rv=value: (self.cleanup(rv) and False))

    @classmethod
    def allcommands(cls):
        all_commands = []
        subclasses = cls.__subclasses__()
        while True:
            all_commands.extend(
                [s for s in subclasses if not (s.name.startswith('_'))])
            newsubclasses = []
            for sc in [x for x in [c.__subclasses__()
                                   for c in subclasses] if x]:
                newsubclasses.extend(sc)
            subclasses = newsubclasses
            if not subclasses:
                break
        del subclasses
        return all_commands

    @classmethod
    def __str__(cls):
        return cls.name

    def do_return(self, retval):
        logger.debug('Returning from command {} with value {}'.format(self.name, retval))


def cleanup_commandline(commandline):
    """Clean up the commandline: remove trailing spaces and comments"""

    commandline = commandline.strip()  # remove trailing whitespace
    instring = None
    for i in range(len(commandline)):
        if commandline[i] in ['"', "'"]:
            if instring == commandline[i]:
                instring = None
            elif instring is None:
                instring = commandline[i]
        if (commandline[i] == '#') and (instring is None):
            return commandline[:i].strip()
    if instring is not None:
        raise ValueError('Unterminated string in command line', commandline)
    return commandline.strip()
