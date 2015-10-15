from gi.repository import GLib
from .command import Command


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

    timeout = 60

    def execute(self, instrument, arglist, namespace):
        devicename = arglist[0]
        variablename = arglist[1]
        self._require_device(instrument, devicename)
        self._install_timeout_handler(self.timeout)
        self._check_for_variable = variablename
        instrument.devices[devicename].refresh_variable(variablename)

    def on_variable_change(self, device, variable, newvalue):
        if variable == self._check_for_variable:
            self._uninstall_timeout_handler()
            self._unrequire_device()
            self.emit('return', newvalue)
        return False


class Help(Command):
    """Get help on the command

    Invocation: help(<commandname>)

    Arguments:
        <commandname>: the name of the command

    Remarks:
        a help text is printed
    """
    name = 'help'

    def execute(self, instrument, arglist, namespace):
        cmdname = arglist[0]
        GLib.idle_add(
            lambda m='Help on command ' + cmdname + ':\n' + instrument.commands[cmdname].__doc__: self._idlefunc(m))

    def _idlefunc(self, msg):
        self.emit('message', msg)
        self.emit('return', msg)
        return False


class What(Command):
    """List the contents of the current namespace

    Invocation: what()

    Arguments: None

    Remarks: None
    """
    name = 'what'

    def execute(self, instrument, arglist, namespace):
        GLib.idle_add(
            lambda m=', '.join([str(k) for k in namespace.keys()]): self._idlefunc(m))

    def _idlefunc(self, msg):
        self.emit('message', msg)
        self.emit('return', msg)
