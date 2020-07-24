from typing import Any

from .command import Command


class BeamStop(Command):
    name = 'beamstop'
    timerinterval = None

    def initialize(self, arguments: Any):
        if arguments[0] not in ['in', 'out']:
            raise self.CommandException('Argument must be either "in" or "out".')
        for motor in [self.instrument.beamstop.motorx(), self.instrument.beamstop.motory()]:
            motor.moving.connect(self.onMotorMotion)
        self.instrument.beamstop.stateChanged.connect(self.onBeamstopStateChanged)
        if arguments[0].lower() == 'in':
            self.instrument.beamstop.moveIn()
        else:
            self.instrument.beamstop.moveOut()

    def onMotorMotion(self, actualposition: float, startposition: float, endposition: float):
        self.progress.emit(f'Moving motor {self.sender().name}, now at {actualposition:.4f}',
                           int((actualposition - startposition) / (endposition - startposition) * 1000), 1000)

    def onBeamstopStateChanged(self, newstate: str):
        if newstate == self.arguments[0]:
            self.finish(self.arguments[0])

    def stop(self):
        self.instrument.beamstop.motorx().stop()
        self.instrument.beamstop.motory().stop()
        self.fail('Stopping command on user request')

    def disconnectSignals(self):
        self.instrument.beamstop.stateChanged.disconnect(self.onBeamstopStateChanged)
        for motor in [self.instrument.beamstop.motorx(), self.instrument.beamstop.motory()]:
            motor.moving.disconnect(self.onMotorMotion)
