import time

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

    def execute(self, interpreter, arglist, instrument, namespace):
        devicename = arglist[0]
        variablename = arglist[1]
        self._require_device(instrument, devicename)
        self._install_timeout_handler(self.timeout)
        self._check_for_variable = variablename
        try:
            instrument.devices[devicename].refresh_variable(variablename)
        except NotImplementedError:
            # there are variables which cannot be queried
            self._uninstall_timeout_handler()
            self._unrequire_device(None)
            GLib.idle_add(lambda dev=instrument.devices[devicename], var=variablename, val=instrument.devices[
                          devicename].get_variable(variablename): self.on_variable_change(dev, var, val) and False)

    def on_variable_change(self, device, variable, newvalue):
        if variable == self._check_for_variable:
            self._uninstall_timeout_handler()
            self._unrequire_device()
            self.emit('return', newvalue)
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

    timeout = 60

    def execute(self, interpreter, arglist, instrument, namespace):
        devicename = arglist[0]
        variablename = arglist[1]
        value = arglist[2]
        self._require_device(instrument, devicename)
        self._install_timeout_handler(self.timeout)
        self._check_for_variable = value
        try:
            instrument.devices[devicename].set_variable(variablename, value)
        except NotImplementedError:
            # there are variables which cannot be queried
            self._uninstall_timeout_handler()
            self._unrequire_device(None)
            GLib.idle_add(lambda dev=instrument.devices[devicename], var=variablename, val=instrument.devices[
                devicename].get_variable(variablename): self.on_variable_change(dev, var, val) and False)

    def on_variable_change(self, device, variable, newvalue):
        if variable == self._check_for_variable:
            self._uninstall_timeout_handler()
            self._unrequire_device()
            self.emit('return', newvalue)
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

    def execute(self, interpreter, arglist, instrument, namespace):
        devicename = arglist[0]
        commandname = arglist[1]
        device = instrument.devices[devicename]
        device.execute_command(commandname, *(arglist[2:]))
        GLib.idle_add(lambda: self.emit('return', None) and False)


class ListVariable(Command):
    """List the names of all variables of a device

    Invocation: listvars(<device>)

    Arguments:
        <device>: the name of the device

    Remarks:
        the value is returned
    """
    name = 'listvar'

    timeout = 60

    def execute(self, interpreter, arglist, instrument, namespace):
        devicename = arglist[0]
        self._require_device(instrument, devicename)
        self._install_timeout_handler(self.timeout)
        device = instrument.devices[devicename]
        self._idlehandler = GLib.idle_add(
            lambda d=device: self._do_the_listing(device))

    def _do_the_listing(self, device):
        self._uninstall_timeout_handler()
        self._unrequire_device()
        lis = sorted(device.list_variables())
        self.emit('message', ', '.join(lis))
        self.emit('return', lis)

    def on_timeout(self):
        GLib.source_remove(self._idlehandler)
        return Command.on_timeout(self)

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

    def execute(self, interpreter, arglist, instrument, namespace):
        try:
            cmdname = arglist[0]
        except IndexError:
            GLib.idle_add(lambda m='Please give the name of a command as an argument. Known commands: ' +
                          ', '.join(c for c in sorted(interpreter.commands)): self._idlefunc(m))
        else:
            GLib.idle_add(
                lambda m='Help on command ' + cmdname + ':\n' + interpreter.commands[cmdname].__doc__: self._idlefunc(m))

    def _idlefunc(self, msg):
        self.emit('message', msg)
        self.emit('return', '')
        return False


class What(Command):
    """List the contents of the current namespace

    Invocation: what()

    Arguments: None

    Remarks: None
    """
    name = 'what'

    def execute(self, interpreter, arglist, instrument, namespace):
        GLib.idle_add(
            lambda m=', '.join([str(k) for k in namespace.keys()]): self._idlefunc(m))

    def _idlefunc(self, msg):
        self.emit('message', msg)
        self.emit('return', '')


class Echo(Command):
    """Echo the arguments back

    Invocation: echo(<arg1>, <arg2>, ...)

    Arguments:
        arbitrary number and type of arguments

    Remarks: None
    """
    name = 'echo'

    def execute(self, interpreter, arglist, instrument, namespace):
        GLib.idle_add(
            lambda m=', '.join([repr(a) for a in arglist]): self._idlefunc(m))

    def _idlefunc(self, msg):
        self.emit('message', msg)
        self.emit('return', '')

class Print(Echo):
    """A print command similar to that in Python.

    Invocation: print(<arg1>, <arg2>, ...)

    Arguments:
        arbitrary number and type of arguments

    Remarks:
        keyword arguments not supported
    """
    name='print'

    def execute(self, interpreter, arglist, instrument, namespace):
        text=' '.join([str(x) for x in arglist])
        GLib.idle_add(lambda m=text:self._idlefunc(m))


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

    def execute(self, interpreter, arglist, instrument, namespace):
        varname = arglist[0]
        varvalue = arglist[1]
        namespace[varname] = varvalue
        GLib.idle_add(lambda: self.emit('return', varvalue) and False)


class Sleep(Command):
    """Sleep for a given time

    Invocation: sleep(<delay>)

    Arguments:
        <delay>: sleep time in seconds

    Remarks:
        None
    """
    name = 'sleep'

    def execute(self, interpreter, arglist, instrument, namespace):
        self._starttime = time.time()
        self._sleeptime = float(arglist[0])
        self._progress = GLib.timeout_add(500, self._progress)
        self._end = GLib.timeout_add(1000 * self._sleeptime, self.on_end)

    def _progress(self):
        t = time.time()
        self.emit('progress', 'Remaining time from sleep: %.1f sec.' %
                  (self._sleeptime - (t - self._starttime)), (t - self._starttime) / self._sleeptime)
        return True

    def on_end(self):
        GLib.source_remove(self._progress)
        GLib.source_remove(self._end)
        self.emit('return', time.time() - self._starttime)
        return False

    def kill(self):
        GLib.idle_add(self.on_end)


class SaveConfig(Command):
    """Write the config file to disk

    Invocation: saveconfig()

    Arguments:
        None

    Remarks:
        None
    """
    name = 'saveconfig'

    def execute(self, interpreter, arglist, instrument, namespace):
        instrument.save_state()
        GLib.idle_add(lambda: self.emit('return', None) and False)
