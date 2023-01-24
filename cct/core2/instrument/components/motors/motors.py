import itertools
import logging
from typing import Iterator, Any, List, Dict, Union, Optional

import h5py
from PySide6 import QtCore, QtGui
from PySide6.QtCore import Signal, Slot

from .motor import Motor, MotorRole, MotorDirection
from ..auth import Privilege, needsprivilege
from ..component import Component
from ....devices.motor.generic.frontend import MotorController

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Motors(Component, QtCore.QAbstractItemModel):
    motors: List[Motor]

    newMotor = Signal(str)
    motorRemoved = Signal(str)

    def __init__(self, **kwargs):
        self.motors = []
        super().__init__(**kwargs)
        self.instrument.devicemanager.deviceAdded.connect(self.onDeviceConnectedOrDisconnected)
        self.instrument.devicemanager.deviceRemoved.connect(self.onDeviceConnectedOrDisconnected)

    def loadFromConfig(self):
        logger.debug('Loading Motors state from config')
        motorkeys = list(self.cfg.setdefault('motors', []))
        motorkeys_newstyle = [k for k in motorkeys if self.cfg['motors',  k,  'name'] == k]
        motorkeys_oldstyle = [k for k in motorkeys if k not in motorkeys_newstyle]

        for motorkey in itertools.chain(motorkeys_newstyle, motorkeys_oldstyle):
            logger.debug(f'Motor key: {motorkey}')
            motorinfo = self.cfg['motors',  motorkey]
            if motorinfo['name'] in self:
                logger.debug(f'Motor {motorinfo["name"]} with {motorkey=} already exists, not adding')
                if motorkey != motorinfo['name']:
                    del self.cfg['motors',  motorkey]
                    logger.debug(f'Deleted old-style motor information {motorkey=}, '
                                 f'corresponding to motor name {motorinfo["name"]} from the config.')
                    continue
            direction = motorinfo.setdefault('direction', None)
            role = motorinfo.setdefault('role', None)
            self._addmotor(
                motorinfo['name'],
                motorinfo['controller'],
                motorinfo['index'],
                role=None if role is None else MotorRole(role),
                direction=None if direction is None else MotorDirection(direction))

    @Slot(str)
    def onDeviceConnectedOrDisconnected(self, name: str):
        # If a motor controller is disconnected or connected
        for i, motor in enumerate(self.motors):
            if motor.controllername == name:
                self.dataChanged.emit(
                    self.index(i, 0, QtCore.QModelIndex()),
                    self.index(i, self.columnCount(), QtCore.QModelIndex())
                )

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 9

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self.motors)

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            return \
                ['Motor name', 'Left limit', 'Right limit', 'Position', 'Speed', 'Left switch', 'Right switch', 'Load',
                 'Status flags'][section]

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            try:
                if index.column() == 0:  # motor name
                    return self.motors[index.row()].name
                elif index.column() == 1:  # left limit
                    return f"{self.motors[index.row()].get('softleft'):.4f}"
                elif index.column() == 2:  # right limit
                    return f"{self.motors[index.row()].get('softright'):.4f}"
                elif index.column() == 3:  # position
                    return f"{self.motors[index.row()].get('actualposition'):.4f}"
                elif index.column() == 4:  # speed
                    return f"{self.motors[index.row()].get('actualspeed'):.4f}"
                elif index.column() in [5, 6]:  # left and right switches
                    return None  # CheckStateRole will show the switch status
                elif index.column() == 7:
                    return self.motors[index.row()].get('load')
                elif index.column() == 8:
                    return self.motors[index.row()].get('drivererror')
            except (KeyError, MotorController.DeviceError):
                # happens when a controller is missing
                return None
        elif role == QtCore.Qt.ItemDataRole.CheckStateRole:
            try:
                if index.column() == 5:
                    return QtCore.Qt.CheckState.Checked if self.motors[index.row()].get('leftswitchstatus') else QtCore.Qt.CheckState.Unchecked
                elif index.column() == 6:
                    return QtCore.Qt.CheckState.Checked if self.motors[index.row()].get('rightswitchstatus') else QtCore.Qt.CheckState.Unchecked
            except (KeyError, MotorController.DeviceError):
                # happens when a controller is missing
                return None
        elif role == QtCore.Qt.ItemDataRole.BackgroundRole:
            try:
                return QtGui.QColor('lightgreen') if self.motors[index.row()].get('moving') else None
            except (KeyError, MotorController.DeviceError):
                # happens when a controller is missing
                return None
        elif role == QtCore.Qt.ItemDataRole.FontRole:
            if index.column() == 3:
                font = QtGui.QFont()
                font.setBold(True)
                return font
        elif role == QtCore.Qt.ItemDataRole.UserRole:
            return self.motors[index.row()]
        elif (role == QtCore.Qt.ItemDataRole.DecorationRole) and (index.column() == 0):
            if self.motors[index.row()].role == MotorRole.Sample:
                return QtGui.QIcon(QtGui.QPixmap(":/icons/sample.svg"))
            elif self.motors[index.row()].role == MotorRole.BeamStop:
                return QtGui.QIcon(QtGui.QPixmap(":/icons/beamstop-in.svg"))
            elif self.motors[index.row()].role == MotorRole.Pinhole:
                return QtGui.QIcon(QtGui.QPixmap(":/icons/pinhole.svg"))
            else:
                return None
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        motor = self.motors[index.row()]
        if motor.hasController:
            return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
        else:
            return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsSelectable

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def _addmotor(self, motorname: str, devicename: str, motorindex: int,
                  role: Optional[MotorRole] = None, direction: Optional[MotorDirection] = None):
        logger.debug(f'Adding motor {motorname=}.')
        if any([motor.name == motorname for motor in self.motors]):
            # motor already exists.
            raise ValueError('Motor already exists')
        # maintain sorting order
        motorsbeforethis = [i for i, m in enumerate(self.motors) if m.name < motorname]
        if not motorsbeforethis:
            insert_at = 0
        else:
            insert_at = max(motorsbeforethis) + 1
        self.beginInsertRows(QtCore.QModelIndex(), insert_at, 1)
        motor = Motor(self.instrument, devicename, motorindex, motorname)
        self.motors.insert(insert_at, motor)
        motor.started.connect(self.onMotorStarted)
        motor.stopped.connect(self.onMotorStopped)
        motor.variableChanged.connect(self.onMotorVariableChanged)
        motor.positionChanged.connect(self.onMotorPositionChanged)
        self.endInsertRows()
        self.newMotor.emit(motorname)
        self.cfg['motors',  motorname] = {'controller': devicename, 'index': motorindex, 'name': motorname,
                                          'role': motor.role.value, 'direction': motor.direction.value}

    def get(self, item: Union[str, int]) -> Motor:
        if isinstance(item, str):
            try:
                return [m for m in self.motors if m.name == item][0]
            except IndexError:
                raise KeyError(item)
        else:
            return self.motors[item]

    @Slot(float)
    def onMotorPositionChanged(self, position: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        row = self.motors.index(motor)
        self.dataChanged.emit(
            self.index(row, 0, QtCore.QModelIndex()),
            self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex())
        )

    @Slot(float)
    def onMotorStarted(self, startposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        row = self.motors.index(motor)
        self.dataChanged.emit(
            self.index(row, 0, QtCore.QModelIndex()),
            self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    @Slot(bool, float)
    def onMotorStopped(self, success: bool, endposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        row = self.motors.index(motor)
        self.dataChanged.emit(
            self.index(row, 0, QtCore.QModelIndex()),
            self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))
        if (self._panicking == self.PanicState.Panicking) and (not [m for m in self.motors if m.isMoving()]):
            super().panichandler()

    @Slot(str, object, object)
    def onMotorVariableChanged(self, name: str, value: Any, prevvalue: Any):
        motor = self.sender()
        assert isinstance(motor, Motor)
        row = self.motors.index(motor)
        if name in ['softleft', 'softright', 'actualposition', 'actualspeed', 'leftswitchstatus', 'rightswitchstatus',
                    'load', 'drivererror']:
            self.dataChanged.emit(
                self.index(row, 0, QtCore.QModelIndex()),
                self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def iterMotors(self) -> Iterator[Motor]:
        return iter(self.motors)

    def __contains__(self, item: Union[Motor, str]) -> bool:
        if isinstance(item, Motor):
            return item in self.motors
        else:
            return bool([m for m in self.motors if m.name == item])

    def __len__(self) -> int:
        return len(self.motors)

    def getHeaderEntry(self) -> Dict[str, float]:
        return {m.name: m.where() for m in self.motors}

    @needsprivilege(Privilege.MotorConfiguration, 'Not enough privileges to add motors')
    def addMotor(self, motorname: str, controllername: str, axis: int, softleft: float, softright: float,
                 position: float, role: Optional[MotorRole] = None, direction: Optional[MotorDirection] = None):
        if motorname in self:
            raise ValueError(f'A motor already exists with name "{motorname}"')
        # ensure that some roles and directions are unique
        for role_, direction_ in [(MotorRole.BeamStop, MotorDirection.X), (MotorRole.BeamStop, MotorDirection.Y),
                                  (MotorRole.Sample, MotorDirection.X), (MotorRole.Sample, MotorDirection.Y)]:
            if (role_ == role) and (direction_ == direction_) and [m for m in self if
                                                                   (m.role == role) and (m.direction == direction)]:
                raise ValueError(f'Another motor already exists with role {role} and direction {direction}')
        controller = self.instrument.devicemanager.get(controllername)
        assert isinstance(controller, MotorController)
        if axis >= controller.Naxes:
            raise ValueError(f'Controller {controllername} has only {controller.Naxes} axes.')
        if axis < 0:
            raise ValueError('The lowest axis number is zero.')
        if [m for m in self.motors if (m.controllername == controllername) and (m.axis == axis)]:
            raise ValueError(f'A motor already exists for controller {controllername} and axis {axis}')
        if softright < softleft:
            raise ValueError(f'Left limit must be lower than the right one.')
        if (position < softleft) or (position > softright):
            raise ValueError(f'Position must be between the limits.')
        self._addmotor(motorname, controllername, axis, role, direction)
        self.get(motorname).setLimits(softleft, softright)
        self.get(motorname).setPosition(position)

    @needsprivilege(Privilege.MotorConfiguration, 'Not enough privileges to remove a motor')
    def removeMotor(self, motorname: str):
        index = [i for i, m in enumerate(self.motors) if m.name == motorname][0]
        self.beginRemoveRows(QtCore.QModelIndex(), index, index)
        self.motors[index].started.disconnect(self.onMotorStarted)
        self.motors[index].stopped.disconnect(self.onMotorStopped)
        self.motors[index].variableChanged.disconnect(self.onMotorVariableChanged)
        self.motors[index].positionChanged.disconnect(self.onMotorPositionChanged)
        self.motorRemoved.emit(motorname)
        del self.motors[index]
        self.endRemoveRows()

    def getMotorForRoleAndDirection(self, role: MotorRole, direction: MotorDirection) -> Motor:
        candidates = [m for m in self.motors if m.direction == direction and m.role == role]
        if not candidates:
            raise KeyError(f'No motor for {role=}, {direction=}')
        if len(candidates) > 1:
            raise KeyError(f'More than motor fulfils the criteria {role=}, {direction=}')
        return candidates[0]

    @property
    def sample_x(self) -> Motor:
        return self.getMotorForRoleAndDirection(MotorRole.Sample, MotorDirection.X)

    @property
    def sample_y(self) -> Motor:
        return self.getMotorForRoleAndDirection(MotorRole.Sample, MotorDirection.Y)

    @property
    def beamstop_x(self) -> Motor:
        return self.getMotorForRoleAndDirection(MotorRole.BeamStop, MotorDirection.X)

    @property
    def beamstop_y(self) -> Motor:
        return self.getMotorForRoleAndDirection(MotorRole.BeamStop, MotorDirection.Y)

    def panichandler(self):
        self._panicking =self.PanicState.Panicking
        for m in self.motors:
            if m.isMoving():
                m.stop()
        if not [m for m in self.motors if m.isMoving()]:
            super().panichandler()

    def toNeXus(self, instrumentgroup: h5py.Group) -> h5py.Group:
        for motor in self.iterMotors():
            mg = instrumentgroup.create_group(motor.name)
            mg.attrs['target'] = mg.name  # NeXus requires this attribute for hard-linked groups/datasets
            motor.toNeXus(mg)
        return instrumentgroup
