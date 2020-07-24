import logging
from typing import Iterator, Any, List

from PyQt5 import QtCore, QtGui

from .component import Component
from ...devices.motor.generic.frontend import MotorController

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Motor(QtCore.QObject):
    controllername: str
    axis: int
    name: str

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
            logger.debug('Move started of motor {self.name}')
            self.started.emit(startposition)

    def onMoveEnded(self, motor: int, success: bool, endposition: float):
        if motor == self.axis:
            logger.debug(f'Move ended of motor {self.name}')
            self.stopped.emit(success, endposition)

    def moveTo(self, position: float):
        return self.controller.moveTo(self.axis, position)

    def moveRel(self, position: float):
        return self.controller.moveRel(self.axis, position)

    def stop(self):
        return self.controller.stopMotor(self.axis)

    def isMoving(self) -> bool:
        return self.controller[f'moving${self.axis}']

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
            if all([x.timestamp > moving.timestamp for x in [actpos, startpos, endpos]]):
                # if all variables are more recent than the start of the motion:
                self.moving.emit(actpos.value, startpos.value, endpos.value)

    @property
    def controller(self) -> MotorController:
        return self.instrument.devicemanager[self.controllername]


class Motors(QtCore.QAbstractItemModel, Component):
    motors: List[Motor]

    newMotor = QtCore.pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.motors = []
        self.instrument.devicemanager.deviceConnected.connect(self.onDeviceConnected)
        self.instrument.devicemanager.deviceDisconnected.connect(self.onDeviceDisconnected)

    def onDeviceDisconnected(self, name: str, expected: bool):
        if expected:
            for motorname in [m.name for m in self.motors]:
                motor = [m for m in self.motors if m.name == motorname][0]
                if motor.controller.name == name:
                    idx = self.motors.index(motor)
                    self.beginRemoveRows(QtCore.QModelIndex(), idx, idx)
                    motor.deleteLater()
                    self.motors.remove(motor)
                    self.endRemoveRows()

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 9

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self.motors)

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return \
                ['Motor name', 'Left limit', 'Right limit', 'Position', 'Speed', 'Left switch', 'Right switch', 'Load',
                 'Status flags'][section]

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:  # motor name
                return self.motors[index.row()].name
            elif index.column() == 1:  # left limit
                return f"{self.motors[index.row()]['softleft']:.4f}"
            elif index.column() == 2:  # right limit
                return f"{self.motors[index.row()]['softright']:.4f}"
            elif index.column() == 3:  # position
                return f"{self.motors[index.row()]['actualposition']:.4f}"
            elif index.column() == 4:  # speed
                return f"{self.motors[index.row()]['actualspeed']:.4f}"
            elif index.column() in [5, 6]:  # left and right switches
                return None  # CheckStateRole will show the switch status
            elif index.column() == 7:
                return self.motors[index.row()]['load']
            elif index.column() == 8:
                return self.motors[index.row()]['drivererror']
        elif role == QtCore.Qt.CheckStateRole:
            if index.column() == 5:
                return QtCore.Qt.Checked if self.motors[index.row()]['leftswitchstatus'] else QtCore.Qt.Unchecked
            elif index.column() == 6:
                return QtCore.Qt.Checked if self.motors[index.row()]['rightswitchstatus'] else QtCore.Qt.Unchecked
        elif role == QtCore.Qt.BackgroundColorRole:
            return QtGui.QColor('lightgreen') if self.motors[index.row()]['moving'] else None
        elif role == QtCore.Qt.FontRole:
            if index.column() == 3:
                font = QtGui.QFont()
                font.setBold(True)
                return font
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def onDeviceConnected(self, name: str):
        device = self.instrument.devicemanager.devices[name]
        if device.devicetype == 'motorcontroller':
            assert isinstance(device, MotorController)
            for key in self.config['motors']:
                if self.config['motors'][key]['controller'] == name:
                    motorname = self.config['motors'][key]['name']
                    motorindex = self.config['motors'][key]['index']
                    if any([motor.name == motorname for motor in self.motors]):
                        # motor already exists.
                        continue
                    # maintain sorting order
                    motorsbeforethis = [i for i, m in enumerate(self.motors) if m.name < motorname]
                    if not motorsbeforethis:
                        insert_at = 0
                    else:
                        insert_at = max(motorsbeforethis) + 1
                    self.beginInsertRows(QtCore.QModelIndex(), insert_at, 1)
                    motor = Motor(self.instrument, name, motorindex, motorname)
                    self.motors.insert(insert_at, motor)
                    motor.started.connect(self.onMotorStarted)
                    motor.stopped.connect(self.onMotorStopped)
                    motor.variableChanged.connect(self.onMotorVariableChanged)
                    self.endInsertRows()
                    self.newMotor.emit(motorname)

    def __getitem__(self, item: str) -> Motor:
        return [m for m in self.motors if m.name == item][0]

    def onMotorStarted(self, startposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        row = self.motors.index(motor)
        self.dataChanged.emit(
            self.index(row, 0, QtCore.QModelIndex()),
            self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()),
            [QtCore.Qt.BackgroundColorRole])

    def onMotorStopped(self, success: bool, endposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        row = self.motors.index(motor)
        self.dataChanged.emit(
            self.index(row, 0, QtCore.QModelIndex()),
            self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()),
            [QtCore.Qt.BackgroundColorRole])

    def onMotorVariableChanged(self, name: str, value: Any, prevvalue: Any):
        motor = self.sender()
        assert isinstance(motor, Motor)
        row = self.motors.index(motor)
        if name in ['softleft', 'softright', 'actualposition', 'actualspeed', 'leftswitchstatus', 'rightswitchstatus',
                    'load', 'drivererror']:
            self.dataChanged.emit(
                self.index(row, 0, QtCore.QModelIndex()),
                self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def __iter__(self) -> Iterator[Motor]:
        return iter(self.motors)

    def __contains__(self, item) -> bool:
        return item in self.motors
