import time
import traceback

from .command import Command, CommandArgumentError
from ..services.samples import Sample
from ..utils.timeout import TimeOut


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
        self._sleeptimeout = TimeOut(self.sleeptime * 1000, lambda: self.cleanup(None) and False)
        self._starttime = time.monotonic()
        self.emit('message', 'Sleeping for {:.2f} seconds.'.format(self.sleeptime))

    def on_pulse(self):
        spent_time = time.monotonic() - self._starttime
        self.emit('progress', 'Remaining time from sleep: {:.1f} sec.'.format(
            (self.sleeptime - spent_time)), spent_time / self.sleeptime)
        return True

    def cleanup(self, *args, **kwargs):
        if self._sleeptimeout is not None:
            self._sleeptimeout.stop()
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

class CopySample(Command):
    """Make a copy of a sample

    Invocation: copysample(<oldname>, <newname>)

    Arguments:
        <oldname>: the name of the sample to be copied
        <newname>: the name of the new sample

    Remarks:
        None
    """
    name = 'copysample'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args)!=2:
            raise CommandArgumentError('Command {} requires exactly two arguments.'.format(self.name))

    def execute(self):
        try:
            sample = self.instrument.services['samplestore'].get_sample(self.args[0])
        except KeyError as ke:
            self.emit('fail', ke, traceback.format_exc())
            self.idle_return(None)
        else:
            assert isinstance(sample, Sample)
            copied = Sample(sample)
            copied.title=self.args[1]
            self.instrument.services['samplestore'].set_sample(copied.title, copied)
            self.emit('message', 'Copied sample "{}" to "{}"'.format(self.args[0], self.args[1]))
            self.idle_return(self.args[1])