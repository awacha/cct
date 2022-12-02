from PySide6.QtCore import Slot


from .command import Command
from .commandargument import StringChoicesArgument


class BeamStopCommand(Command):
    name = 'beamstop'
    timerinterval = None
    description = 'Move the beam-stop'
    arguments = [StringChoicesArgument('state', 'The requested state of the beam-stop', ['in', 'out', 'IN', 'OUT'])]
    requestedstate: bool=None

    def initialize(self, requestedstate: str):
        if requestedstate.lower() not in ['in', 'out']:
            raise self.CommandException('Argument must be either "in" or "out".')
        if requestedstate.lower() == 'in':
            self.requestedstate = True
        elif requestedstate.lower() == 'out':
            self.requestedstate = False
        else:
            raise self.CommandException(
                f'Invalid argument to command beamstop: {requestedstate}. Must be either "in" or "out".')
        self.instrument.beamstop.stateChanged.connect(self.onBeamstopStateChanged)
        self.instrument.beamstop.movingProgress.connect(self.onBeamstopMovingProgress)
        self.instrument.beamstop.movingFinished.connect(self.onBeamstopMovingFinished)
        if self.requestedstate:
            self.instrument.beamstop.moveIn()
        else:
            self.instrument.beamstop.moveOut()
        self.message.emit(f'Moving beamstop {"in" if requestedstate else "out"}.')

    @Slot(bool)
    def onBeamstopMovingFinished(self, success: bool):
        self.disconnectSignals()
        if success:
            self.finish(self.requestedstate)
        else:
            self.fail('Moving the beam-stop failed.')

    @Slot(str, float, float, float)
    def onBeamstopMovingProgress(self, message: str, start: float, end: float, current: float):
        self.progress.emit(message, int(1000*(current-start)/(end-start)), 1000)

    def stop(self):
        self.instrument.beamstop.stopMoving()
        self.message.emit('Stopping command on user request')

    def disconnectSignals(self):
        self.instrument.beamstop.stateChanged.disconnect(self.onBeamstopStateChanged)
        self.instrument.beamstop.movingFinished.disconnect(self.onBeamstopMovingFinished)
        self.instrument.beamstop.movingProgress.disconnect(self.onBeamstopMovingProgress)

    @Slot(str)
    def onBeamstopStateChanged(self, state: str):
        pass