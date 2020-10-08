from PyQt5 import QtCore

import enum

import logging
from typing import Iterator, Any

from ....devices.motor.generic.frontend import MotorController
from ..auth.privilege import Privilege

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MotorRole(enum.Enum):
    Sample = 'sample'
    BeamStop = 'beamstop'
    Pinhole = 'pinhole'
    Other = 'other'


class MotorDirection(enum.Enum):
    X = 'x'
    Y = 'y'
    Z = 'z'
    Other = 'other'


class Motor(QtCore.QObject):
    controllername: str
    axis: int
    name: str
    role: MotorRole = MotorRole.Other
    direction: MotorDirection = MotorDirection.Other

    started = QtCore.pyqtSignal(float)  # emitted when a move is started. Argument: start position
    stopped = QtCore.pyqtSignal(bool, float)  # emitted when a move is finished. Arguments: success, end position
    variableChanged = QtCore.pyqtSignal(str, object, object)  # emitted whenever a variable changes
    positionChanged = QtCore.pyqtSignal(float)  # emitted when the position changes either by movement or by calibration
    moving = QtCore.pyqtSignal(float, float, float)  # arguments: actual position, start position, target position

    def __init__(self, instrument: "Instrument", controllername: str, axis: int, name: str):
        super().__init__()
        self.instrument = instrument
        self.controllername = controllername
        self.axis = axis
        self.name = name
        self.controller.moveStarted.connect(self.onMoveStarted)
        self.controller.moveEnded.connect(self.onMoveEnded)
        self.controller.variableChanged.connect(self.onVariableChanged)

    def onMoveStarted(self, motor: int, startposition: float):
        if motor == self.axis:
            logger.debug(f'Move started of motor {self.name}')
            self.started.emit(startposition)

    def onMoveEnded(self, motor: int, success: bool, endposition: float):
        if motor == self.axis:
            logger.debug(f'Move ended of motor {self.name}')
            self.stopped.emit(success, endposition)

    def moveTo(self, position: float):
        if (self.role == MotorRole.BeamStop) and (not self.instrument.auth.hasPrivilege(Privilege.MoveBeamstop)):
            raise RuntimeError('Cannot move beamstop: insufficient privileges')
        elif (self.role == MotorRole.Pinhole) and (not self.instrument.auth.hasPrivilege(Privilege.MovePinholes)):
            raise RuntimeError('Cannot move pinhole: insufficient privileges')
        return self.controller.moveTo(self.axis, position)

    def moveRel(self, position: float):
        if (self.role == MotorRole.BeamStop) and (not self.instrument.auth.hasPrivilege(Privilege.MoveBeamstop)):
            raise RuntimeError('Cannot move beamstop: insufficient privileges')
        elif (self.role == MotorRole.Pinhole) and (not self.instrument.auth.hasPrivilege(Privilege.MovePinholes)):
            raise RuntimeError('Cannot move pinhole: insufficient privileges')
        return self.controller.moveRel(self.axis, position)

    def stop(self):
        return self.controller.stopMotor(self.axis)

    def isMoving(self) -> bool:
        return self.controller[f'moving${self.axis}']

    def setPosition(self, newposition: float):
        if (self.role == MotorRole.BeamStop) and (not self.instrument.auth.hasPrivilege(Privilege.MoveBeamstop)):
            raise RuntimeError('Cannot move beamstop: insufficient privileges')
        elif (self.role == MotorRole.Pinhole) and (not self.instrument.auth.hasPrivilege(Privilege.MovePinholes)):
            raise RuntimeError('Cannot move pinhole: insufficient privileges')
        if not self.instrument.auth.hasPrivilege(Privilege.MotorCalibration):
            raise RuntimeError('Cannot calibrate motor: insufficient privileges')
        return self.controller.setPosition(self.axis, newposition)

    def setLimits(self, left: float, right: float):
        if (self.role == MotorRole.BeamStop) and (not self.instrument.auth.hasPrivilege(Privilege.MoveBeamstop)):
            raise RuntimeError('Cannot move beamstop: insufficient privileges')
        elif (self.role == MotorRole.Pinhole) and (not self.instrument.auth.hasPrivilege(Privilege.MovePinholes)):
            raise RuntimeError('Cannot move pinhole: insufficient privileges')
        if not self.instrument.auth.hasPrivilege(Privilege.MotorCalibration):
            raise RuntimeError('Cannot calibrate motor: insufficient privileges')
        return self.controller.setLimits(self.axis, left, right)

    def where(self) -> float:
        return self.controller[f'actualposition${self.axis}']

    def keys(self) -> Iterator[str]:
        for key in self.controller.keys():
            if '$' in key:
                basename, motoridx = key.split('$')
                if int(motoridx) == self.axis:
                    yield basename

    def __getitem__(self, item: str) -> Any:
        return self.controller[f'{item}${self.axis}']

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        if '$' not in variablename:
            # disregard non per-axis variables
            return
        basename, axis = variablename.split('$')
        if int(axis) != self.axis:
            # disregards variables for other motors
            return
        self.variableChanged.emit(basename, newvalue, previousvalue)
        if (basename == 'actualposition') and isinstance(newvalue, float):
            # the position is changed either by motion or by calibration
            self.positionChanged.emit(newvalue)
            # see if it changed because the motor is moving.
            controller = self.controller
            moving = controller.getVariable(f'moving${self.axis}')
            if not moving.value:
                # the motor is not moving
                return
            # the motor is in motion. See if the start position and the target position and the actual position have
            # been updated since the start.
            actpos = self.controller.getVariable(f'actualposition${self.axis}')
            startpos = self.controller.getVariable(f'movestartposition${self.axis}')
            endpos = self.controller.getVariable(f'targetposition${self.axis}')
            if actpos.timestamp > moving.timestamp:
                # if all variables are more recent than the start of the motion:
                self.moving.emit(actpos.value, startpos.value, endpos.value)

    @property
    def controller(self) -> MotorController:
        return self.instrument.devicemanager[self.controllername]
