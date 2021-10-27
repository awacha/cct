import logging
from typing import Any, List, Iterator

from PyQt5 import QtCore

from .component import Component
from ...devices.device.frontend import DeviceFrontend
from ...sensors.sensor import Sensor
from ....utils import getIconFromTheme

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Sensors(QtCore.QAbstractItemModel, Component):
    _data: List[Sensor]

    def __init__(self, **kwargs):
        self._data = []
        super().__init__(**kwargs)
        self.instrument.devicemanager.deviceAdded.connect(self.onDeviceAdded)
        self.instrument.devicemanager.deviceRemoved.connect(self.onDeviceRemoved)
        for device in self.instrument.devicemanager:
            self.onDeviceAdded(device.name)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 3

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Sensor', 'Device', 'Reading'][section]

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        s = self._data[index.row()]
        if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
            return s.name
        elif (index.column() == 1) and (role == QtCore.Qt.DisplayRole):
            return s.devicename
        elif (index.column() == 2) and (role == QtCore.Qt.DisplayRole):
            if s.isUnknown():
                return '-- Unknown --'
            return f'{s.value():.4f} {s.units}'
        elif (index.column() == 0) and (role == QtCore.Qt.DecorationRole):
            if s.isOK():
                return getIconFromTheme('answer-correct', 'answer', 'emblem-ok')
            elif s.isWarning():
                return getIconFromTheme('data-warning', 'dialog-warning')
            elif s.isError():
                return getIconFromTheme('data-error', 'dialog-error')
            elif s.isUnknown():
                return getIconFromTheme('question', 'dialog-question')

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def onDeviceAdded(self, name: str):
        device: DeviceFrontend = self.instrument.devicemanager[name]
        for sensor in device.sensors:
            self.beginInsertRows(QtCore.QModelIndex(), len(self._data), len(self._data))
            self._data.append(sensor)
            sensor.valueChanged.connect(self.onSensorValueChanged)
            sensor.warning.connect(self.onSensorWarning)
            sensor.error.connect(self.onSensorError)
            sensor.ok.connect(self.onSensorOk)
            sensor.unknown.connect(self.onSensorUnknown)
            self.endInsertRows()

    def onDeviceRemoved(self, name: str, expected: bool):
        while len(sensorstobedeleted := [s for s in self._data if s.devicename == name]):
            idx = self._data.index(sensorstobedeleted[0])
            self.beginRemoveRows(QtCore.QModelIndex(), idx, idx)
            sensorstobedeleted[0].valueChanged.disconnect(self.onSensorValueChanged)
            sensorstobedeleted[0].error.disconnect(self.onSensorError)
            sensorstobedeleted[0].warning.disconnect(self.onSensorWarning)
            sensorstobedeleted[0].ok.disconnect(self.onSensorOk)
            sensorstobedeleted[0].unknown.disconnect(self.onSensorUnknown)
            del self._data[idx]
            self.endRemoveRows()

    def onSensorValueChanged(self, newvalue: float):
        logger.debug(f'Sensor {self.sender().name} value changed to {self.sender().value()} =? {newvalue}')
        idx = self._data.index(self.sender())
        self.dataChanged.emit(self.index(idx, 0, QtCore.QModelIndex()),
                              self.index(idx, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def onSensorWarning(self):
        logger.debug(f'Sensor {self.sender().name} is {self.sender()._errorstate}')
        idx = self._data.index(self.sender())
        self.dataChanged.emit(self.index(idx, 0, QtCore.QModelIndex()),
                              self.index(idx, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def onSensorError(self):
        logger.debug(f'Sensor {self.sender().name} is {self.sender()._errorstate}')
        idx = self._data.index(self.sender())
        self.dataChanged.emit(self.index(idx, 0, QtCore.QModelIndex()),
                              self.index(idx, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def onSensorOk(self):
        logger.debug(f'Sensor {self.sender().name} is {self.sender()._errorstate}')
        idx = self._data.index(self.sender())
        self.dataChanged.emit(self.index(idx, 0, QtCore.QModelIndex()),
                              self.index(idx, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def onSensorUnknown(self):
        logger.debug(f'Sensor {self.sender().name} is {self.sender()._errorstate}')
        idx = self._data.index(self.sender())
        self.dataChanged.emit(self.index(idx, 0, QtCore.QModelIndex()),
                              self.index(idx, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def __iter__(self) -> Iterator[Sensor]:
        yield from self._data
