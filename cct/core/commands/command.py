import traceback
import weakref

from gi.repository import GLib

from ..utils.callback import Callbacks, SignalFlags


class CommandError(Exception):
    pass


class CommandTimeoutError(CommandError):
    pass


class Command(Callbacks):
    """This is an abstract base class for a command, which can be issued in
    order to do something on the instrument, e.g. move a motor or take an
    exposure.

    The `name` class variable is the command name: this will be used to
    determine which command has to be run from a command line.

    The most important part is the `execute()` method, which _starts_ the
    operation, then returns. This method gets three arguments: `instrument`,
    which is the singleton object corresponding to the whole beamline, from
    which all the devices and state variables can be obtained. The second one
    is the argument list of this command. The last argument is a dictionary of the
    environment (namespace) the command runs in.

    The `simulate()` should do everything as `execute()` can, without talking
    to devices.  

    When the command is finished, the 'return' signal should be emitted and 
    the results of the command, i.e. a scattering pattern, a floating point
    variable, or any kind of Python object must be sent. This signal MUST be
    emitted even if some error or failure happened.

    Failures can be signaled through the 'fail' signal: its first argument
    is the exception object, the second one is the formatted traceback.

    Long-running commands might want to emit the 'pulse' or 'progress' signals
    frequently, thus the user interface can have a clue if the command is
    still running or not.

    Other signals can also be defined by the user.

    The member function kill() signifies the running command that it should
    stop and emit the 'return' signal immediately, or as soon as possible.
    Short-running commands (runtime is at most 5 seconds) might ignore this
    function.

    As a general rule, signals must not be emitted from the execute, simulate
    and kill member functions. Use idle functions or callbacks for this.
    """
    __signals__ = {
        # emitted when the command completes. Must be emitted exactly once.
        # This also must be the last signal emitted by the command.
        'return': (SignalFlags.RUN_FIRST, None, (object,)),
        # emitted on a failure. Can be emitted multiple times
        'fail': (SignalFlags.RUN_LAST, None, (object, str)),
        # long running commands where the duration cannot be
        # estimated in advance, should emit this periodically (say
        # in every second)
        'pulse': (SignalFlags.RUN_FIRST, None, (str,)),
        # long running commands where the duration can be estimated
        # in advance, this should be emitted periodically (e.g. in
        # every second)
        'progress': (SignalFlags.RUN_FIRST, None, (str, float)),
        # send occasional messages to the command interpreter (to
        # be written to a terminal or logged at the INFO level.
        'message': (SignalFlags.RUN_FIRST, None, (str,)),
        # can be sent to give the front-end command-dependent details.
        # A typical use case is the transmission command, which uses
        # this mechanism to notify the front-end of what it has
        # currently been doing. The single argument of this signal
        # depends on the command.
        'detail': (SignalFlags.RUN_FIRST, None, (object,))
    }

    name = '__abstract__'

    required_devices = []

    timeout = None  # seconds

    pulse_interval = None  # seconds

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

    def validate(self):
        """Check the validity of self.args and self.kwargs.

        If everything is OK, it should return True. Otherwise
        an appropriate exception, a subclass of CommandError
        should be raised."""
        return True

    def _execute(self):
        if not self.validate():
            raise CommandError('Validation of command parameters failed.')
        self._connect_devices()
        if self.timeout is not None:
            self._timeout_handler = GLib.timeout_add(self.timeout * 1000, self.on_timeout)
        if self.pulse_interval is not None:
            self._pulse_handler = GLib.timeout_add(self.pulse_interval * 1000, self.on_pulse)

        return self.execute()

    def execute(self):
        """Start the execution of the command."""
        raise NotImplementedError

    def kill(self):
        """Stop running the current command."""
        pass

    def cleanup(self, returnvalue: object = None):
        """Must be called after execution finished."""
        if self._timeout_handler is not None:
            GLib.source_remove(self._timeout_handler)
        if self._pulse_handler is not None:
            GLib.source_remove(self._pulse_handler)
        self._disconnect_devices()
        self.emit('return', returnvalue)

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
            dev = self.interpreter.instrument.devices[d]
            self._device_connections[d] = [dev.connect('variable-change', self.on_variable_change),
                                           dev.connect('error', self.on_error),
                                           dev.connect('disconnect', self.on_disconnect),
                                           ]

    def _disconnect_devices(self):
        for d in list(self._device_connections.keys()):
            dev = self.interpreter.instrument.devices[d]
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
