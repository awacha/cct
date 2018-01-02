import logging

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
        device.execute_command(self.cmdname, *self.cmdargs)
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


