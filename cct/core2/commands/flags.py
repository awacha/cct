from .command import Command


class NewFlag(Command):
    name = 'newflag'
    timerinterval = 0

    def initialize(self, arguments: str):
        self.instrument.interpreter.flags.addFlag(arguments, False)


class SetFlag(Command):
    name = 'setflag'
    timerinterval = 0

    def initialize(self, arguments: str):
        self.instrument.interpreter.flags.setFlag(arguments, True)


class ClearFlag(Command):
    name = 'clearflag'
    timerinterval = 0

    def initialize(self, arguments: str):
        self.instrument.interpreter.flags.setFlag(arguments, False)
