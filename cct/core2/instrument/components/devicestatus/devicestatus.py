from typing import Any, List, Tuple, Optional, Dict
import logging

from PyQt5 import QtCore

from ..component import Component
from ....devices.device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DeviceStatus(QtCore.QAbstractItemModel, Component):
    _devicenames: List[str]
    _deviceready: Dict[str, bool]
    __indexobjects: List[Tuple[Optional[int], int]]

    def __init__(self, **kwargs):
        self._devicenames = []
        self.__indexobjects = []
        self._deviceready = {}
        super().__init__(**kwargs)

    def startComponent(self):
        self.instrument.devicemanager.deviceAdded.connect(self.onDeviceAdded)
        self.instrument.devicemanager.deviceRemoved.connect(self.onDeviceRemoved)
        for device in self.instrument.devicemanager:
            self.onDeviceAdded(device.name)

    def stopComponent(self):
        self.beginResetModel()
        for device in self._devicenames:
            self.onDeviceRemoved(device, True)
        self._devicenames = []
        self.endResetModel()
        self.instrument.devicemanager.deviceAdded.disconnect(self.onDeviceAdded)
        self.instrument.devicemanager.deviceRemoved.disconnect(self.onDeviceRemoved)

    def panichandler(self):
        super().panichandler()

    def onDeviceAdded(self, name: str):
        # assume that self._devicenames is already sorted
        assert self._devicenames == sorted(self._devicenames)
        insertrow = max([i for i, n in enumerate(self._devicenames) if n < name] + [-1]) + 1
        self.beginInsertRows(QtCore.QModelIndex(), insertrow, insertrow)
        self._devicenames.insert(insertrow, name)
        self.endInsertRows()
        device: DeviceFrontend = self.instrument.devicemanager[name]
        self._deviceready[name] = device.ready
        device.allVariablesReady.connect(self.onDeviceReadyOrLost)
        device.connectionLost.connect(self.onDeviceReadyOrLost)
        device.connectionEnded.connect(self.onDeviceReadyOrLost)
        device.variableChanged.connect(self.onVariableChanged)

    def onDeviceReadyOrLost(self):
        device: DeviceFrontend = self.sender()
        if device.name not in self._devicenames:
            return
        if (not self._deviceready[device.name]):
            # the device just became ready
            self.beginInsertRows(self.index(self._devicenames.index(device.name), 0, QtCore.QModelIndex()), 0,
                                 len(device) - 1)
            self._deviceready[device.name] = True
            self.endInsertRows()
        else:
            # the device just became "unready": connection lost
            self.beginRemoveRows(self.index(self._devicenames.index(device.name), 0, QtCore.QModelIndex()), 0,
                                 len(device) - 1)
            self._deviceready[device.name] = False
            self.endRemoveRows()

    def onDeviceRemoved(self, name: str, expected: bool):
        logger.debug(f'Device {name} removed')
        assert self._devicenames == sorted(self._devicenames)
        row = self._devicenames.index(name)
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._devicenames[row]
        self.endRemoveRows()
        try:
            device = self.instrument.devicemanager[name]
        except KeyError:
            return
        device.allVariablesReady.disconnect(self.onDeviceReadyOrLost)
        device.connectionLost.disconnect(self.onDeviceReadyOrLost)
        device.connectionEnded.disconnect(self.onDeviceReadyOrLost)
        device.variableChanged.disconnect(self.onVariableChanged)

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        device: DeviceFrontend = self.sender()
        variablenames = sorted(device.keys())
        parent = self.index(self._devicenames.index(device.name), 0, QtCore.QModelIndex())
        index = self.index(variablenames.index(name), 1, parent)
        self.dataChanged.emit(index, index)

    def rowCount(self, parent: QtCore.QModelIndex) -> int:
        if not parent.isValid():
            return len(self._devicenames)
        else:
            device = self.instrument.devicemanager[self._devicenames[parent.row()]]
            if self._deviceready[device.name]:
                return len(device)
            else:
                return 0

    def columnCount(self, parent: QtCore.QModelIndex) -> int:
        return 2

    def index(self, row: int, column: int, parent: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not parent.isValid():
            # top-level, i.e. device index
            try:
                indexdata = [idx for idx in self.__indexobjects if idx[0] is None and idx[1] == row][0]
            except IndexError:
                indexdata = (None, row)
                self.__indexobjects.append(indexdata)
        else:
            # device variable index
            try:
                indexdata = [idx for idx in self.__indexobjects if idx[0] == parent.row() and idx[1] == row][0]
            except IndexError:
                indexdata = (parent.row(), row)
                self.__indexobjects.append(indexdata)
        return self.createIndex(row, column, indexdata)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if child.internalPointer()[0] is None:
            return QtCore.QModelIndex()
        else:
            return self.index(child.internalPointer()[0], 0, QtCore.QModelIndex())

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if index.internalPointer()[0] is None:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (role == QtCore.Qt.DisplayRole) and (orientation == QtCore.Qt.Horizontal):
            return ['Name', 'Value'][section]
        return None

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if index.internalPointer()[0] is None:
            # top-level item, i.e. device name
            if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
                return self._devicenames[index.row()]
            elif (index.column() == 1) and (role == QtCore.Qt.DisplayRole):
                return self.instrument.devicemanager[self._devicenames[index.row()]].devicename
            elif (index.column() == 0) and (role == QtCore.Qt.EditRole):
                return self._devicenames[index.row()]
        else:
            device: DeviceFrontend = self.instrument.devicemanager[self._devicenames[index.parent().row()]]
            varnames = sorted(device.keys())
            variable = device.getVariable(varnames[index.row()])
            if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
                return variable.name
            elif (index.column() == 1) and (role == QtCore.Qt.DisplayRole):
                return variable.value
            elif (index.column() == 0) and (role == QtCore.Qt.EditRole):
                return variable.name
