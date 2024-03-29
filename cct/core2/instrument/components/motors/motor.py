import enum
import logging
import math
from typing import Iterator, Any, Optional

import h5py
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from ..auth.privilege import Privilege
from ....devices.device.frontend import DeviceFrontend
from ....devices.motor.generic.frontend import MotorController
from ....devices.motor.trinamic.frontend import UnitConverter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MotorRole(enum.Enum):
    Sample = 'sample'
    BeamStop = 'beamstop'
    Pinhole = 'pinhole'
    Other = 'other'
    Any = 'any'


class MotorDirection(enum.Enum):
    X = 'x'
    Y = 'y'
    Z = 'z'
    Other = 'other'
    Any = 'any'


class Motor(QtCore.QObject):
    controllername: str
    axis: int
    name: str
    role: MotorRole = MotorRole.Other
    direction: MotorDirection = MotorDirection.Other

    started = Signal(float)  # emitted when a move is started. Argument: start position
    stopped = Signal(bool, float)  # emitted when a move is finished. Arguments: success, end position
    variableChanged = Signal(str, object, object)  # emitted whenever a variable changes
    positionChanged = Signal(float)  # emitted when the position changes either by movement or by calibration
    moving = Signal(float, float, float)  # arguments: actual position, start position, target position
    cameOnLine = Signal()  # emitted when the controller becomes on-line
    wentOffLine = Signal()  # emitted when the controller becomes off-line

    def __init__(self, instrument: "Instrument", controllername: str, axis: int, name: str,
                 role: Optional[MotorRole] = None, direction: Optional[MotorDirection] = None):
        super().__init__()
        self.instrument = instrument
        self.controllername = controllername
        self.axis = axis
        self.name = name
        if direction is None:
            if self.name.upper().endswith('X'):
                direction = MotorDirection.X
            elif self.name.upper().endswith('Y'):
                direction = MotorDirection.Y
            elif self.name.upper().endswith('Z'):
                direction = MotorDirection.Z
            else:
                direction = MotorDirection.Other
        self.direction = direction
        if role is None:
            if self.name.upper().startswith('SAMPLE'):
                role = MotorRole.Sample
            elif self.name.upper().startswith('PH') or self.name.upper().startswith('PINHOLE'):
                role = MotorRole.Pinhole
            elif self.name.upper().startswith('BS') or self.name.upper().startswith('BEAMSTOP'):
                role = MotorRole.BeamStop
            else:
                role = MotorRole.Other
        self.role = role

        self.instrument.devicemanager[self.controllername].allVariablesReady.connect(self.onControllerConnected)
        self.instrument.devicemanager[self.controllername].connectionLost.connect(self.onControllerDisconnected)
        if self.instrument.devicemanager[self.controllername].isOnline():
            self.onControllerConnected()

    @Slot()
    def onControllerConnected(self):
        logger.debug(f'Connecting slots of motor {self.name} to controller {self.controllername}')
        self.controller.moveStarted.connect(self.onMoveStarted)
        self.controller.moveEnded.connect(self.onMoveEnded)
        self.controller.variableChanged.connect(self.onVariableChanged)
        self.cameOnLine.emit()

    @Slot(bool)
    def onControllerDisconnected(self, expected: bool):
        try:
            self.controller.moveStarted.disconnect(self.onMoveStarted)
            self.controller.moveEnded.disconnect(self.onMoveEnded)
            self.controller.variableChanged.disconnect(self.onVariableChanged)
        except (KeyError, TypeError):
            # happens if the controller has been removed or it has failed to initialize
            pass
        self.wentOffLine.emit()

    @Slot(int, float)
    def onMoveStarted(self, motor: int, startposition: float):
        if motor == self.axis:
            logger.debug(f'Move started of motor {self.name}')
            self.started.emit(startposition)

    @Slot(int, bool, float)
    def onMoveEnded(self, motor: int, success: bool, endposition: float):
        if motor == self.axis:
            logger.debug(f'Move ended of motor {self.name}')
            self.stopped.emit(success, endposition)

    def moveTo(self, position: float):
        self.checkPrivileges(calibration=False)
        return self.controller.moveTo(self.axis, position)

    def moveRel(self, position: float):
        self.checkPrivileges(calibration=False)
        return self.controller.moveRel(self.axis, position)

    def stop(self):
        return self.controller.stopMotor(self.axis)

    def isMoving(self) -> bool:
        return self.controller[f'moving${self.axis}']

    def setPosition(self, newposition: float):
        self.checkPrivileges(calibration=True)
        return self.controller.setPosition(self.axis, newposition)

    def setLimits(self, left: float, right: float):
        self.checkPrivileges(calibration=True)
        return self.controller.setLimits(self.axis, left, right)

    def where(self) -> float:
        try:
            return self.controller[f'actualposition${self.axis}']
        except DeviceFrontend.DeviceError:
            return math.nan

    def keys(self) -> Iterator[str]:
        for key in self.controller.keys():
            if '$' in key:
                basename, motoridx = key.split('$')
                if int(motoridx) == self.axis:
                    yield basename

    def __getitem__(self, item: str) -> Any:
        return self.controller[f'{item}${self.axis}']

    @Slot(str, object, object)
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

    @property
    def hasController(self) -> bool:
        return self.isOnline()

    def checkPrivileges(self, calibration: bool):
        if (self.role == MotorRole.BeamStop) and (not self.instrument.auth.hasPrivilege(Privilege.MoveBeamstop)):
            raise RuntimeError('Cannot move beamstop: insufficient privileges')
        elif (self.role == MotorRole.Pinhole) and (not self.instrument.auth.hasPrivilege(Privilege.MovePinholes)):
            raise RuntimeError('Cannot move pinhole: insufficient privileges')
        if calibration and (not self.instrument.auth.hasPrivilege(Privilege.MotorCalibration)):
            raise RuntimeError('Cannot calibrate motor: insufficient privileges')

    def isOnline(self) -> bool:
        return (self.controllername in self.instrument.devicemanager) and self.instrument.devicemanager[
            self.controllername].isOnline()

    def unitConverter(self) -> UnitConverter:
        return self.controller.unitConverter(self.axis)

    def isAtRightSoftLimit(self) -> bool:
        return self.where() >= self['softright']

    def isAtLeftSoftLimit(self) -> bool:
        return self.where() <= self['softleft']

    def isAtRightHardLimit(self) -> bool:
        return self['rigthswitchenable'] and self['rightswitchstatus']

    def isAtLeftHardLimit(self) -> bool:
        return self['leftswitchenable'] and self['leftswitchstatus']

    @staticmethod
    def create_hdf5_dataset(grp: h5py.Group, name: str, data: Any, **kwargs) -> h5py.Dataset:
        return DeviceFrontend.create_hdf5_dataset(grp, name, data, **kwargs)

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        grp.attrs['NX_class'] = 'NXpositioner'
        self.create_hdf5_dataset(grp, 'name', self.name)
        self.create_hdf5_dataset(grp, 'description', self.role.value + ' motor in direction ' + self.direction.value)
        self.create_hdf5_dataset(grp, 'value', self['actualposition'])
        self.create_hdf5_dataset(grp, 'raw_value', self['actualposition:raw'])
        self.create_hdf5_dataset(grp, 'target_value', self['targetposition'])
        self.create_hdf5_dataset(grp, 'soft_limit_min', self['softleft'])
        self.create_hdf5_dataset(grp, 'soft_limit_max', self['softright'])
        self.create_hdf5_dataset(grp, 'velocity', self['actualspeed'])
        self.create_hdf5_dataset(grp, 'acceleration_time', self['maxspeed'] / self['maxacceleration'], units='s')
        return grp
