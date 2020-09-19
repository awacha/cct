from typing import Any

from .command import Command, InstantCommand
from .commandargument import StringArgument


class NewFlag(InstantCommand):
    name = 'newflag'
    description = 'Create a new flag'
    arguments = [StringArgument('flag', 'Name of the flag')]

    def run(self, arguments: Any) -> Any:
        self.instrument.interpreter.flags.addFlag(arguments, False)


class SetFlag(Command):
    name = 'setflag'
    description = 'Set a flag to True'
    arguments = [StringArgument('flag', 'Name of the flag')]

    def run(self, arguments: Any) -> Any:
        self.instrument.interpreter.flags.setFlag(arguments, True)


class ClearFlag(Command):
    name = 'clearflag'
    description = 'Clear the flag (set it to False)'
    arguments = [StringArgument('flag', 'Name of the flag')]

    def run(self, arguments: Any) -> Any:
        self.instrument.interpreter.flags.setFlag(arguments, False)
