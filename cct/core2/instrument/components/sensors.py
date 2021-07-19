from .component import Component
from PyQt5 import QtCore
from typing import Any, List
from ...sensors.sensor import Sensor
from ...devices.device.frontend import DeviceFrontend


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
            return f'{s.value():.4f} {s.units}'
    
    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def onDeviceAdded(self, name: str):
        device: DeviceFrontend = self.instrument.devicemanager[name]
        for sensor in device.sensors:
            self.beginInsertRows(QtCore.QModelIndex(), len(self._data), len(self._data))
            self._data.append(sensor)
            sensor.valueChanged.connect(self.onSensorValueChanged)
            self.endInsertRows()

    def onDeviceRemoved(self, name: str, expected: bool):
        while len(sensorstobedeleted := [s for s in self._data if s.devicename == name]):
            idx = self._data.index(sensorstobedeleted[0])
            self.beginRemoveRows(QtCore.QModelIndex(), idx, idx)
            sensorstobedeleted[0].valueChanged.disconnect(self.onSensorValueChanged)
            del self._data[idx]
            self.endRemoveRows()

    def onSensorValueChanged(self, newvalue: float):
        idx = self._data.index(self.sender())
        self.dataChanged.emit(self.index(idx, 2, QtCore.QModelIndex()), self.index(idx, 2, QtCore.QModelIndex()))
