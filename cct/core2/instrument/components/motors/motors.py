import logging
from typing import Iterator, Any, List, Dict

from PyQt5 import QtCore, QtGui

from ..component import Component
from ....devices.motor.generic.frontend import MotorController
from .motor import Motor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
        try:
            return [m for m in self.motors if m.name == item][0]
        except IndexError:
            raise KeyError(item)

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

    def getHeaderEntry(self) -> Dict[str, float]:
        return {m.name: m.where() for m in self.motors}
