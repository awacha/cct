import logging
import time

from gi.repository import GLib

from .command import Command, CommandArgumentError
from ..devices.device import Device

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GetVariable(Command):
    """Get the value of a device variable

    Invocation: getvar(<device>, <variable>)

    Arguments:
        <device>: the name of the device
        <variable>: the name of the variable

    Remarks:
        the value is returned
    """
    name = 'getvar'

    timeout = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 2:
            raise CommandArgumentError('Command {} needs exactly two positional arguments.'.format(self.name))
        self.devicename = str(self.args[0])
        self.variablename = str(self.args[1])
        self.required_devices = [self.devicename]

    def execute(self):
        dev = self.get_device(self.devicename)
        assert isinstance(dev, Device)
        dev.refresh_variable(self.variablename)

    def on_variable_change(self, device, variable, newvalue):
        if variable == self.variablename:
            self.cleanup(newvalue)
        return False


class SetVariable(Command):
    """Set the value of a device variable

    Invocation: setvar(<device>, <variable>, <value>)

    Arguments:
        <device>: the name of the device
        <variable>: the name of the variable
        <value>: the new value

    Remarks:
        This command does not return until the change has been verified.
        It returns the updated value of the device variable, which may be
        slightly different from the requested one (quantization, hardware
        limitations etc.)

        Use with care! Setting wrong values (e.g. coil current limits for
        motor controllers) may cause permanent hardware damage!
    """
    name = 'setvar'

    timeout = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 3:
            raise CommandArgumentError('Command {} needs exactly three positional arguments.'.format(self.name))
        self.devicename = str(self.args[0])
        self.variablename = str(self.args[1])
        self.value = self.args[2]
        self.required_devices = [self.devicename]

    def execute(self):
        dev = self.get_device(self.devicename)
        assert isinstance(dev, Device)
        dev.set_variable(self.variablename, self.value)
        dev.refresh_variable(self.variablename)

    def on_variable_change(self, device, variable, newvalue):
        if variable == self.variablename:
            self.cleanup(newvalue)
        return False


class DevCommand(Command):
    """Execute a low-level command on a device

    Invocation: devcommand(<device>, <commandname>, <arg1>, <arg2>, ...)

    Arguments:
        <device>: the name of the device
        <commandname>: the name of the low-level command
        <arg1...>: arguments needed for that command

    Remarks:
        This command returns immediately.
    """

    name = 'devcommand'

    timeout = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) < 2:
            raise CommandArgumentError('Command {} needs at least two positional arguments.'.format(self.name))
        self.devicename = str(self.args[0])
        self.cmdname = str(self.args[1])
        self.cmdargs = self.args[2:]
        self.required_devices = [self.devicename]

    def execute(self):
        device = self.get_device(self.devicename)
        device.execute_command(self.cmdname, *(self.cmdargs))
        self.idle_return(None)


class ListVariables(Command):
    """List the names of all variables of a device

    Invocation: listvars(<device>)

    Arguments:
        <device>: the name of the device

    Remarks:
        the value is returned
    """
    name = 'listvar'

    timeout = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} needs exactly one positional argument.'.format(self.name))
        self.devicename = str(self.args[0])

    def execute(self):
        dev = self.get_device(self.devicename)
        assert isinstance(dev, Device)
        lis = dev.list_variables()
        self.emit('message', ', '.join(lis))
        self.idle_return(lis)


class Help(Command):
    """Get help on the command

    Invocation: help(<commandname>)

    Arguments:
        <commandname>: the name of the command

    Remarks:
        a help text is printed
    """
    name = 'help'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) > 1:
            raise CommandArgumentError('Command {} needs at most one positional argument.'.format(self.name))
        try:
            self.commandname = str(self.args[0])
        except IndexError:
            self.commandname = None

    def execute(self):
        if self.commandname is None:
            msg = 'Please give the name of a command as an argument. Known commands: ' + \
                  ', '.join([cmd for cmd in sorted(self.interpreter.commands)])
        else:
            msg = 'Help on command ' + self.commandname + ':\n' + self.interpreter.commands[self.commandname].__doc__
        self.emit('message', msg)
        self.idle_return(msg)


class What(Command):
    """List the contents of the current namespace

    Invocation: what()

    Arguments: None

    Remarks: None
    """
    name = 'what'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if self.args:
            raise CommandArgumentError('Command {} does not support positional arguments.'.format(self.name))

    def execute(self):
        self.emit('message', ', '.join(self.namespace.keys()))
        self.idle_return(list(self.namespace.keys()))


class Echo(Command):
    """Echo the arguments back

    Invocation: echo(<arg1>, <arg2>, ...)

    Arguments:
        arbitrary number and type of arguments

    Remarks: None
    """
    name = 'echo'

    def execute(self):
        msg = ', '.join([repr(a) for a in self.args])
        self.emit('message', msg)
        self.emit('return', self.args)


class Print(Command):
    """A print command similar to that in Python.

    Invocation: print(<arg1>, <arg2>, ...)

    Arguments:
        arbitrary number and type of arguments

    Remarks:
        keyword arguments not supported
    """
    name = 'print'

    def execute(self):
        text = ' '.join([str(x) for x in self.args])
        self.emit('message', text)
        self.emit('return', None)


class Set(Command):
    """Set value of script variable

    Invocation: set(<variable name>, <expression>)

    Arguments:
        <variable name>: a string (!)
        <expression>: an expression 

    Remarks:
        After running this command, the named variable will be created or 
        updated to the evaluated value of expression
    """
    name = 'set'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 2:
            raise CommandArgumentError('Command {} requires exactly two positional arguments.'.format(self.name))
        self.varname = str(self.args[0])
        self.value = self.args[1]

    def execute(self):
        self.namespace[self.varname] = self.value
        self.idle_return(self.value)

class Sleep(Command):
    """Sleep for a given time

    Invocation: sleep(<delay>)

    Arguments:
        <delay>: sleep time in seconds

    Remarks:
        None
    """
    name = 'sleep'

    pulse_interval = 0.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly one positional argument.'.format(self.name))
        self.sleeptime = float(self.args[0])
        self._sleeptimeout = None
        self._starttime = None

    def execute(self):
        self._sleeptimeout = GLib.timeout_add(self.sleeptime * 1000, lambda: self.cleanup(None) and False)
        self._starttime = time.monotonic()
        self.emit('message', 'Sleeping for {:.2f} seconds.'.format(self.sleeptime))

    def on_pulse(self):
        spent_time = time.monotonic() - self._starttime
        self.emit('progress', 'Remaining time from sleep: {:.1f} sec.'.format(
            (self.sleeptime - spent_time), spent_time / self.sleeptime))
        return True

    def cleanup(self, *args, **kwargs):
        if self._sleeptimeout is not None:
            GLib.source_remove(self._sleeptimeout)
            self._sleeptimeout = None
        super().cleanup(*args, **kwargs)

class SaveConfig(Command):
    """Write the config file to disk

    Invocation: saveconfig()

    Arguments:
        None

    Remarks:
        None
    """
    name = 'saveconfig'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if self.args:
            raise CommandArgumentError('Command {} does not support positional arguments.'.format(self.name))

    def execute(self):
        self.instrument.save_state()
        self.emit('message', 'Configuration saved.')
        self.idle_return(None)
