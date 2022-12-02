from typing import Any

from .command import InstantCommand
from .commandargument import StringArgument


class NewFlag(InstantCommand):
    name = 'newflag'
    description = 'Create a new flag'
    arguments = [StringArgument('flag', 'Name of the flag')]

    def run(self, arguments: Any) -> Any:
        self.message.emit(f'Creating a new flag with name "{arguments}"')
        self.instrument.interpreter.flags.addFlag(arguments, False)


class SetFlag(InstantCommand):
    name = 'setflag'
    description = 'Set a flag to True'
    arguments = [StringArgument('flag', 'Name of the flag')]

    def run(self, arguments: Any) -> Any:
        self.message.emit(f'Setting flag "{arguments}" to true')
        self.instrument.interpreter.flags.setFlag(arguments, True)


class ClearFlag(InstantCommand):
    name = 'clearflag'
    description = 'Clear the flag (set it to False)'
    arguments = [StringArgument('flag', 'Name of the flag')]

    def run(self, arguments: Any) -> Any:
        self.message.emit(f'Clearing flag "{arguments}"')
        self.instrument.interpreter.flags.setFlag(arguments, False)
