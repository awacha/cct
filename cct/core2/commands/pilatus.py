from .command import Command
from .commandargument import StringChoicesArgument, FloatArgument
from ..devices.detector import PilatusDetector, PilatusGain


class Trim(Command):
    name = 'trim'
    description = 'Trim the Pilatus detector'
    arguments = [FloatArgument('threshold', 'Lower discriminator threshold (eV)'),
                 StringChoicesArgument('gain', 'Gain setting', ['lowG', 'midG', 'highG'])]

    def connectPilatus(self):
        pass

    def disconnectPilatus(self):
        pass

    def initialize(self, threshold: float, gain: str):
        try:
            gain = [g for g in PilatusGain if g.value.lower() == gain][0]
        except IndexError:
            raise self.CommandException(f'Invalid gain setting: {gain}')
        self.connectPilatus()