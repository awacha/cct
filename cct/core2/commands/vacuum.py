from PySide6 import QtCore

from .command import Command, InstantCommand
from .commandargument import FloatArgument
from ..devices.vacuumgauge import VacuumGauge


class Vacuum(InstantCommand):
    name='vacuum'
    arguments = []
    description = 'Get the vacuum pressure (in mbars)'

    def run(self) -> float:
        pressure = self.instrument.devicemanager.vacuum().pressure()
        self.message.emit(f'Vacuum pressure is {pressure} mbar')
        return pressure


class WaitVacuum(Command):
    name = 'wait_vacuum'
    arguments = [FloatArgument('pressure_limit', 'the upper limit of the allowed pressure (exclusive)')]
    description = 'Wait until the vacuum pressure becomes lower than a given threshold'
    pressure_limit: float
    vacgauge: VacuumGauge
    timerinterval = 0.5

    def initialize(self, pressure_limit: float):
        self.pressure_limit = pressure_limit
        self.vacgauge = self.instrument.devicemanager.vacuum()
        self.message.emit(
            f'Waiting for vacuum pressure to go below {self.pressure_limit:.4f} mbar.')

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        pressure = self.vacgauge.pressure()
        if pressure < self.pressure_limit:
            self.message.emit(
                f'Vacuum pressure is {pressure:.4f} mbar, below the expected threshold {self.pressure_limit:.4f} mbar')
            self.finish(pressure)
        else:
            self.progress.emit(
                f'Waiting for vacuum pressure to go below {self.pressure_limit:.4f} mbar. Now at {pressure:.4f} mbar.',
                0, 0)
