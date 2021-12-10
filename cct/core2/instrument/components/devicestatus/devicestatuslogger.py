from typing import Any, Optional, List, Tuple

import numpy as np
from PyQt5 import QtCore

class RecordedVariable:
    devicename: str
    variablename: str
    scaling: float = 1.0
    def __init__(self, devicename: str, variablename: str, scaling: float=1.0):
        self.devicename = devicename
        self.variablename = variablename
        self.scaling = scaling


class DeviceStatusLogger(QtCore.QAbstractItemModel):
    _filename: Optional[str] = None
    _period: float = 5.0
    _variables: List[RecordedVariable]
    _devicemanager: "DeviceManager"
    _record: Optional[np.ndarray] = None
    _nrecord: int = 1000

    def __init__(self, devicemanager: "DeviceManager", filename: Optional[str] = None, period: float = 5.0):
        self._filename = filename
        self._period = period
        self._variables = []
        self._devicemanager = devicemanager
        super().__init__()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._variables)
    
    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 3
    
    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)
    
    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable
    
    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
            return self._variables[index.row()].devicename
        elif (index.column() == 0) and (role == QtCore.Qt.EditRole):
            return self._variables[index.row()].devicename
        elif (index.column() == 0) and (role == QtCore.Qt.UserRole):
            return sorted(self._devicemanager.devicenames())
        elif (index.column() == 1) and (role == QtCore.Qt.DisplayRole):
            return self._variables[index.row()].variablename
        elif (index.column() == 1) and (role == QtCore.Qt.EditRole):
            return self._variables[index.row()].variablename
        elif (index.column() == 1) and (role == QtCore.Qt.UserRole):
            return sorted(self._devicemanager[self._variables[index.row()].devicename].keys())
        elif (index.column() == 2) and (role == QtCore.Qt.DisplayRole):
            return f'{self._variables[index.row()].scaling:.6g}'
        elif (index.column() == 2) and (role == QtCore.Qt.EditRole):
            return self._variables[index.row()].scaling
        elif (index.column() == 2) and (role == QtCore.Qt.UserRole):
            return 0, 1e9
        else:
            return None
    
    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        pass
    
    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Device', 'Variable', 'Scaling'][section]
    
    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()
    
    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginRemoveRows(parent, row, row+count-1)
        del self._variables[row:row+count]
        self.endRemoveRows()
        return True

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.removeRows(row, 1, parent)

    def startRecording(self):
        variables =
        self._record =

    def stopRecording(self):
        self._isrecording = False

    def isRecording(self) -> bool:
        return self._record is not None

    def setFileName(self, filename: str):
        self._filename = filename

    def fileName(self) -> str:
        return self._filename

    def addRecordedVariable(self, devicename: str, variablename: str, scaling: float=1.0):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._variables), len(self._variables))
        self._variables.append(RecordedVariable(devicename, variablename, scaling))
        self.endInsertRows()

    def onVariableChanged(self, name:str, newvalue: str, oldvalue: str):
        device = self.sender()
        devname = device.name
        if [v for v in self._variables if v.devicename == devname and v.variablename == name]:
            # a variable has been updated.
            pass

    def getCurrentValues(self) -> Tuple[Any, ...]:
        return tuple([self._devicemanager[v.devicename][v.variablename] for v in self._variables])
