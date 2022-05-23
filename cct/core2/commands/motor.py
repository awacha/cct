from typing import Any

from PyQt5.QtCore import pyqtSlot as Slot

from .command import Command, InstantCommand
from .commandargument import StringArgument, FloatArgument


class MotorCommand(Command):
    motorname: str

    def connectMotor(self):
        self.motor().started.connect(self.onMotorStarted)
        self.motor().stopped.connect(self.onMotorStopped)
        self.motor().moving.connect(self.onMotorMoving)
        self.motor().positionChanged.connect(self.onMotorPositionChanged)

    def disconnectMotor(self):
        self.motor().started.disconnect(self.onMotorStarted)
        self.motor().stopped.disconnect(self.onMotorStopped)
        self.motor().moving.disconnect(self.onMotorMoving)
        self.motor().positionChanged.disconnect(self.onMotorPositionChanged)

    def motor(self):
        return self.instrument.motors[self.motorname]

    @Slot(float)
    def onMotorStarted(self, startposition: float):
        pass

    @Slot(bool, float)
    def onMotorStopped(self, success: bool, endposition: float):
        pass

    @Slot(float, float, float)
    def onMotorMoving(self, where: float, start: float, target: float):
        pass

    @Slot(float)
    def onMotorPositionChanged(self, where: float):
        pass


class MoveTo(MotorCommand):
    name = 'moveto'
    description = 'Move a motor'
    arguments = [StringArgument('motorname', 'The name of the motor to move'),
                 FloatArgument('position', 'Target position')]

    def initialize(self, motorname: str, position:float):
        self.motorname = motorname
        self.connectMotor()
        if self.name == 'moveto':
            self.motor().moveTo(position)
        elif self.name == 'moverel':
            self.motor().moveRel(position)

    @Slot(float, float, float)
    def onMotorMoving(self, where: float, start: float, target: float):
        self.progress.emit(f'Moving motor {self.motorname}. Currently at {where:.4f}', int(1000*(where-start)/(target-start)), 1000)

    @Slot(bool, float)
    def onMotorStopped(self, success: bool, endposition: float):
        self.disconnectMotor()
        if not success:
            self.fail(endposition)
        else:
            self.finish(endposition)

    def stop(self):
        self.motor().stop()
        self.disconnectMotor()
        super().stop()


class MoveRel(MoveTo):
    name = 'moverel'
    description = 'Move a motor relatively to its current position'


class Where(InstantCommand):
    name = 'where'
    description = 'Get current motor position(s)'
    arguments = [StringArgument('motorname', 'The name of the motor ("*" for all)', '*')]

    def run(self, motorname: str) -> Any:
        if motorname == '*':
            positions = {m.name:m.where() for m in self.instrument.motors}
            namelength = max([len(m) for m in positions] + [len("Motor name")])
            txt = f'| {"Motor name":^{namelength}} |  Position  |\n'
            txt += f'+-{"-"*namelength}-+------------+\n'
            for m, p in positions.items():
                txt += f'| {m:^{namelength}} | {p:>10.3f} |\n'
            self.message.emit(txt)
            return positions
        else:
            pos = self.instrument.motors[motorname].where()
            self.message.emit(f'{pos:8.3f}')
            return pos
