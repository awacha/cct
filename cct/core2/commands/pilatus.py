from .command import Command
from .commandargument import StringChoicesArgument, FloatArgument
from ..devices.detector import PilatusDetector, PilatusGain, PilatusBackend


class Trim(Command):
    name = 'trim'
    description = 'Trim the Pilatus detector'
    arguments = [FloatArgument('threshold', 'Lower discriminator threshold (eV)'),
                 StringChoicesArgument('gain', 'Gain setting', ['lowG', 'midG', 'highG'])]

    def pilatus(self) -> PilatusDetector:
        pilatus = self.instrument.devicemanager['pilatus']
        assert isinstance(pilatus, PilatusDetector)
        return pilatus

    def connectPilatus(self):
        self.pilatus().stateChanged.connect(self.onPilatusStateChanged)

    def disconnectPilatus(self):
        self.pilatus().stateChanged.disconnect(self.onPilatusStateChanged)

    def initialize(self, threshold: float, gain: str):
        try:
            gain = [g for g in PilatusGain if g.value.lower() == gain][0]
        except IndexError:
            raise self.CommandException(f'Invalid gain setting: {gain}')
        assert isinstance(gain, PilatusGain)
        if self.pilatus()['__status__'] != PilatusBackend.Status.Idle:
            raise self.CommandException('Cannot trim detector: not idle.')
        self.connectPilatus()
        try:
            self.pilatus().trim(threshold, gain)
        except:
            self.disconnectPilatus()
            raise
        self.progress.emit(f'Trimming detector to {1000*threshold:.0f} keV, {gain.value}', 0,0)
        self.message.emit(f'Trimming detector to {1000*threshold:.0f} keV, {gain.value}')

    def onPilatusStateChanged(self, newstate):
        if newstate == PilatusBackend.Status.Trimming:
            pass
        elif newstate == PilatusBackend.Status.Idle:
            self.finish(True)