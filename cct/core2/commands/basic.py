"""Simple commands"""
import logging
import time

from PyQt5 import QtCore
from typing import Any, Tuple, Optional

from .command import Command, InstantCommand, JumpCommand
from .commandargument import IntArgument, FloatArgument, StringArgument, AnyArgument

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Sleep(Command):
    name = 'sleep'
    description = 'Wait for a given time'
    arguments = [FloatArgument('delay', 'Delay time in seconds')]
    sleeptime: float = None
    starttime: float = None

    def initialize(self, interval: float):
        if interval < 60:
            self.timerinterval = 0.1
        else:
            self.timerinterval = 0.5
        self.sleeptime = interval
        self.starttime = time.monotonic()
        self.message.emit(f'Sleeping for {self.sleeptime:.3f} seconds.')

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        t = time.monotonic() - self.starttime
        if t >= self.sleeptime:
            self.finish(t)
        else:
            self.progress.emit(f'Sleeping for {self.sleeptime:.3f} seconds, {self.sleeptime-t:.1f} seconds remaining', (t / self.sleeptime) * 1000, 1000)


class Comment(InstantCommand):
    name = 'comment'
    description = ''
    arguments = []

    def run(self, *args) -> Any:
        return self.namespace['_']


class Goto(JumpCommand):
    name = 'goto'
    description = 'Unconditional jump to a given label'
    arguments = [StringArgument('label', 'Label name')]

    def run(self, targetlabel: str) -> Any:
        if not isinstance(targetlabel, str):
            raise ValueError('Invalid arguments to command "goto": requires a label name and nothing more.')
        return targetlabel, False


class Gosub(JumpCommand):
    name = 'gosub'
    description = 'Unconditional jump to a label with the possibility of returning later'
    arguments = [StringArgument('label', 'Label name')]

    def run(self, targetlabel: str) -> Any:
        if not isinstance(targetlabel, str):
            raise ValueError('Invalid arguments to command "gosub": requires a label name and nothing more.')
        return targetlabel, True


class Return(JumpCommand):
    name = 'return'
    description = 'Return to the place of a previous "gosub"'
    arguments = []

    def run(self) -> Any:
        return '', False


class GoOnFlag(JumpCommand):
    name = 'goonflag'
    description = 'Conditional jump to a label when a flag is set.'
    arguments = [StringArgument('label', 'Label name'),
                 StringArgument('flag', 'Flag name')]

    def run(self, label:str, flag:str) -> Tuple[Optional[str], bool]:
        if self.instrument.interpreter.flags[flag]:
            return label, False
        else:
            return None, False


class GoSubOnFlag(JumpCommand):
    name = 'gosubonflag'
    description = 'Conditional jump to a label when a flag is set with the possibility of returning later.'
    arguments = [StringArgument('label', 'Label name'),
                 StringArgument('flag', 'Flag name')]

    def run(self, label:str, flag:str) -> Tuple[Optional[str], bool]:
        if self.instrument.interpreter.flags[flag]:
            return label, True
        else:
            return None, False


class GoIf(JumpCommand):
    name = 'goif'
    description = 'Goto a label if a condition is true'
    arguments = [StringArgument('label', 'Label name'),
                 AnyArgument('condition', 'A valid expression that evaluates to True or False')]

    def run(self, label: str, condition: Any) -> Tuple[Optional[str], bool]:
        if bool(condition):
            return label, False
        else:
            return None, False


class GoSubIf(JumpCommand):
    name = 'gosubif'
    description = 'Goto a label (with the possibility of returning) if a condition is true'
    arguments = [StringArgument('label', 'Label name'),
                 AnyArgument('condition', 'A valid expression that evaluates to True or False')]

    def run(self, label: str, condition: Any) -> Tuple[Optional[str], bool]:
        if bool(condition):
            return label, True
        else:
            return None, False


class End(InstantCommand):
    name = 'end'
    description = 'End the script'
    arguments = []

    def run(self, *args: Any) -> Any:
        raise StopIteration()


class Label(InstantCommand):
    name = 'label'
    description = ''
    arguments = []

    def parseArguments(self) -> Any:
        self.parsed_arguments = ()
        return ()

    def run(self, *args: Any) -> Any:
        return None


class Help(InstantCommand):
    name = 'help'
    description = 'Get help on a command'
    arguments = [StringArgument('command', 'Name of the command')]

    def run(self, commandname: str) -> Any:
        try:
            command = [ c for c in Command.subclasses() if c.name == commandname][0]
        except IndexError:
            self.fail(f'Unknown command {commandname}.')
        self.message.emit(f'Help on command {commandname}:\n{command.helptext()}')
        return command.helptext()


class What(InstantCommand):
    name = 'what'
    description =  'Get a list of variables defined in the current namespace'
    arguments = []

    def run(self, *args: Any) -> Any:
        self.message.emit(', '.join(sorted(self.namespace.keys())))
        return sorted(self.namespace.keys())


class Echo(InstantCommand):
    name = 'echo'
    description = 'Echo back the arguments'
    arguments = []

    def run(self, *args: Any) -> Any:
        self.message.emit(', '.join([str(a) for a in args]))
        return True


class Print(InstantCommand):
    name = 'print'
    description = 'Print the arguments'
    arguments = []

    def run(self, *args: Any) -> Any:
        self.message.emit(' '.join([str(a) for a in args]))
        return True


class Set(InstantCommand):
    name = 'set'
    description = 'Set the value of a script variable'
    arguments = [StringArgument('variable', 'Name of the variable'),
                 AnyArgument('expression', 'Value of the variable')]

    def run(self, variable: str, value: Any) -> Any:
        self.namespace[variable] = value


class SaveConfig(InstantCommand):
    name = 'saveconfig'
    description = 'Save the configuration to disk'
    arguments = []

    def run(self, *args: Any) -> Any:
        self.instrument.config.save()
        self.message.emit('Saved configuration to disk.')
        return True