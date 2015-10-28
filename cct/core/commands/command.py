from gi.repository import GObject, GLib
import traceback


class CommandError(Exception):
    pass


class CommandTimeoutError(CommandError):
    pass


class Command(GObject.GObject):
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
    __gsignals__ = {
        # emitted when the command completes. Must be emitted exactly once.
        # This also must be the last signal emitted by the command.
        'return': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        # emitted on a failure. Can be emitted multiple times
        'fail': (GObject.SignalFlags.RUN_LAST, None, (object, str)),
        # long running commands where the duration cannot be
        # estimated in advance, should emit this periodically (say
        # in every second)
        'pulse': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # long running commands where the duration can be estimated
        # in advance, this should be emitted periodically (e.g. in
        # every second)
        'progress': (GObject.SignalFlags.RUN_FIRST, None, (str, float)),
        # send occasional messages to the command interpreter (to
        # be written to a terminal or logged at the INFO level.
        'message': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }

    name = '__abstract__'

    def __init__(self):
        GObject.GObject.__init__(self)
        self._device_connections = {}

    def execute(self, interpreter, arglist, instrument, namespace):
        """Execute the command"""
        raise NotImplementedError

    def simulate(self, instrument, arglist, namespace):
        """Simulate the command. Do everything as execute() would do, just do
        not talk to the devices themselves."""
        raise NotImplementedError

    def kill(self):
        """Stop running the current command."""
        pass

    def _require_device(self, instrument, devicename):
        """Connect to signals `variable-change` and `error` of the given device
        and set up basic signal handlers (on_variable_change() and on_error())."""
        device = instrument.devices[devicename]
        if device in self._device_connections:
            raise CommandError('Device %s already required' % devicename)
        self._device_connections[device] = [device.connect('variable-change', self.on_variable_change),
                                            device.connect(
            'error', self.on_error),
            device.connect('disconnect', self.on_disconnect)]

    def _unrequire_device(self, devicename=None):
        """Disconnect basic signal handlers from the device. If argument
        `devicename` is None, disconnect all signal handlers from all devices."""
        if devicename is None:
            devices = [d._instancename for d in self._device_connections]
        else:
            devices = [devicename]
        for dn in devices:
            try:
                device = [
                    d for d in self._device_connections if d._instancename == dn][0]
            except IndexError:
                continue
            for c in self._device_connections[device]:
                device.disconnect(c)
            del self._device_connections[device]

    def _install_timeout_handler(self, timeout):
        """Install a timeout handler. After `timeout` seconds the command will
        be interrupted and a `fail` signal is sent. Override on_timeout() if
        you want a different behaviour."""
        self._timeout = GLib.timeout_add(1000 * self.timeout, self.on_timeout)

    def _uninstall_timeout_handler(self):
        """Uninstall the timeout handler"""
        try:
            GLib.source_remove(self._timeout)
            del self._timeout
        except AttributeError:
            pass

    def _install_pulse_handler(self, message_or_func, period):
        """Install a pulse handler, which runs periodically (`period` given in
        seconds). If `message_or_func` is a string, the 'pulse' signal will be
        emitted at each run, with `message_or_func` as the argument. Otherwise
        `message_or_func` can be a callable, returning a string as an argument
        for the 'pulse' signal.
        """
        if hasattr(self, '_pulse_handler'):
            self._uninstall_pulse_handler()
        if isinstance(message_or_func, str):
            self._pulse_handler = GLib.timeout_add(
                period * 1000, lambda m=message_or_func: self.emit('pulse', m) or True)
        elif callable(message_or_func):
            self._pulse_handler = GLib.timeout.add(
                period * 1000, lambda m=message_or_func: self.emit('pulse', m()) or True)

    def _uninstall_pulse_handler(self):
        """Uninstall the pulse handler"""
        try:
            GLib.source_remove(self._pulse_handler)
            del self._pulse_handler
        except AttributeError:
            pass

    def on_timeout(self):
        """The timeout handler: called if the command times out.

        Its jobs are:
        1) unrequire all required devices
        2) emit the 'fail' signal with a CommandTimeoutError exception
        3) uninstall timeout handler
        4) uninstall pulse handler

        If you override this, please make sure you do all the jobs above.
        """
        self._unrequire_device()
        try:
            raise CommandTimeoutError('Command %s timed out' % self.name)
        except CommandTimeoutError as exc:
            self.emit('fail', exc, traceback.format_exc())
        self.emit('return', None)
        self._uninstall_timeout_handler()
        self._uninstall_pulse_handler()
        return False

    def on_variable_change(self, device, variablename, newvalue):
        """A basic handler for the variable change in a device. It has been
        written with ONLY ONE required device in mind: it may not work if
        the command requires multiple devices.

        If you want to use this handler, you must make sure that the
        `_check_for_variable` and `_check_for_value` instance variables are
        present. When this handler encounters a situation where the variable,
        the name of which is carried in `_check_for_variable` gets the new
        value `_check_for_value`, it will uninstall possible timeout handlers
        and pulse handlers, unrequire all devices and emit the 'return' signal
        with the new value.
        """
        if hasattr(self, '_check_for_variable') and hasattr(self, '_check_for_value'):
            if (variablename == self._check_for_variable) and (newvalue == self._check_for_value):
                self._uninstall_timeout_handler()
                self._uninstall_pulse_handler()
                self._unrequire_device()
                self.emit('return', newvalue)
        return False

    def on_error(self, device, propname, exc, tb):
        """Emit the 'fail' signal"""
        self.emit('fail', exc, tb)
        return False

    def on_disconnect(self, device, because_of_failure):
        """Emit a fail signal."""
        self.emit('fail', CommandError(
            'Sudden disconnect of device %s' % device._instancename), 'no traceback')
        return False

    @classmethod
    def allcommands(cls):
        all_commands = []
        subclasses = cls.__subclasses__()
        while True:
            all_commands.extend(
                [s for s in subclasses if not(s.name.startswith('_'))])
            subclasses = [x for x in [c.__subclasses__()
                                      for c in subclasses] if x]
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
    # remove comments from command line. Comments are marked by a hash (#)
    # sign. Double hash sign is an escape for the single hash.
    commandline = commandline.replace('##', '__DoUbLeHaSh__')
    try:
        commandline = commandline[:commandline.index('#')]
    except ValueError:
        # if # is not in the commandline
        pass
    commandline.replace('__DoUbLeHaSh__', '#')
    return commandline.strip()
