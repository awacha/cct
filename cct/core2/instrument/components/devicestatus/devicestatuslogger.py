import os.path
import time
from typing import Any, Optional, List, Tuple
import logging

import numpy as np
import numpy.ma as npma
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from ....devices.device.frontend import DeviceFrontend
from ....devices.device.variable import Variable, VariableType

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class RecordedVariable:
    devicename: str
    variablename: str
    scaling: float = 1.0
    vartype: VariableType

    def __init__(self, devicename: str, variablename: str, vartype: VariableType, scaling: float = 1.0):
        self.devicename = devicename
        self.variablename = variablename
        self.scaling = scaling
        self.vartype = vartype


class DeviceStatusLogger(QtCore.QAbstractItemModel):
    name: str
    _filename: Optional[str] = None
    _period: float = 5.0
    _variables: List[RecordedVariable]
    _devicemanager: "DeviceManager"
    _record: Optional[np.ndarray] = None
    _nrecord: int = 1000
    _recordpointer: Optional[int] = None
    _recordtimerhandle: Optional[int] = None
    _writetimerhandle: Optional[int] = None
    _savepointer: Optional[int] = None
    _writeperiod: float = 10.0

    recordingStarted = Signal()
    recordingStopped = Signal()
    newData = Signal(int)
    fileNameChanged = Signal(str)
    periodChanged = Signal(float)
    nrecordChanged = Signal(int)
    nameChanged = Signal(str)

    def __init__(self, devicemanager: "DeviceManager", filename: Optional[str] = None, period: float = 5.0, name: Optional[str] = None):
        self._filename = filename
        self._period = period
        self._variables = []
        self._devicemanager = devicemanager
        self._name = name if name is not None else f'Log{time.monotonic()}'
        super().__init__()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._variables)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 3

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if self.isRecording():
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        else:
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
            device: DeviceFrontend = self._devicemanager[self._variables[index.row()].devicename]
            goodvariablenames = [vn for vn in device.keys() if device.getVariable(vn).vartype in [VariableType.FLOAT, VariableType.INT, VariableType.BOOL]]
            return sorted(goodvariablenames)
        elif (index.column() == 2) and (role == QtCore.Qt.DisplayRole):
            return f'{self._variables[index.row()].scaling:.6g}'
        elif (index.column() == 2) and (role == QtCore.Qt.EditRole):
            return self._variables[index.row()].scaling
        elif (index.column() == 2) and (role == QtCore.Qt.UserRole):
            return 0, 1e9
        else:
            return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if self.isRecording():
            return False
        if (index.column() == 0) and (role == QtCore.Qt.EditRole):
            # device name is to be updated
            if value in self._devicemanager.devicenames:
                self._variables[index.row()].devicename = value
                self._variables[index.row()].variablename = None
                self.dataChanged.emit(
                    self.index(index.row(), 0, QtCore.QModelIndex()),
                    self.index(index.row(), self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))
                return True
        elif (index.column() == 1) and (role == QtCore.Qt.EditRole):
            # variable name is to be updated
            if value in self._devicemanager[self._variables[index.row()].devicename].keys():
                self._variables[index.row()].variablename = value
                self.dataChanged.emit(
                    self.index(index.row(), 0, QtCore.QModelIndex()),
                    self.index(index.row(), self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex())
                )
                return True
        elif (index.column() == 2) and (role == QtCore.Qt.EditRole):
            self._variables[index.row()].scaling = float(value)
            self.dataChanged.emit(
                    self.index(index.row(), 0, QtCore.QModelIndex()),
                    self.index(index.row(), self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex())
                )
            return True
        return False

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Device', 'Variable', 'Scaling'][section]

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginRemoveRows(parent, row, row + count - 1)
        del self._variables[row:row + count]
        self.endRemoveRows()
        return True

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.removeRows(row, 1, parent)

    def startRecording(self):
        if self.isRecording():
            raise RuntimeError('Recording already in progress')
        vartypetodtype = {VariableType.FLOAT: 'f8', VariableType.INT: 'i8', VariableType.BOOL: 'b'}
        dtype = np.dtype([('Time', 'f8')] + [(v.devicename + '/' + v.variablename, vartypetodtype[v.vartype]) for v in
                                             self._variables])
        logger.debug(f'Starting recording of variables {dtype.names[1:]}')
        self._record = npma.empty(self._nrecord, dtype=dtype)
        self._record[:] = npma.masked
        self._recordpointer = 0
        self._savepointer = 0
        if self._recordtimerhandle is not None:
            self.killTimer(self._recordtimerhandle)
            self._recordtimerhandle = None
        self._recordtimerhandle = self.startTimer(int(self._period * 1000), QtCore.Qt.PreciseTimer)
        if self._writetimerhandle is not None:
            self.killTimer(self._writetimerhandle)
            self._writetimerhandle = None
        self._writetimerhandle = self.startTimer(int(self._writeperiod * 1000), QtCore.Qt.PreciseTimer)
        for devicename in {v.devicename for v in self._variables}:
            self._devicemanager[devicename].variableChanged.connect(self.onVariableChanged)
        self.recordingStarted.emit()
        logger.debug(f'Started recording')
        self.recordCurrentValues()

    def stopRecording(self):
        if not self.isRecording():
            raise RuntimeError('No recording in progress')
        logger.debug(f'Stopping recording of variables {self._record.dtype.names[1:]}')
        self.killTimer(self._recordtimerhandle)
        self._recordtimerhandle = None
        self.writeRecord()
        self.killTimer(self._writetimerhandle)
        self._writetimerhandle = None
        self._record = None
        self._savepointer = None
        self._recordpointer = None
        for devicename in {v.devicename for v in self._variables}:
            self._devicemanager[devicename].variableChanged.disconnect(self.onVariableChanged)
        self.recordingStopped.emit()
        logger.debug(f'Stopped recording')

    def isRecording(self) -> bool:
        return self._record is not None

    def setFileName(self, filename: str):
        if self.isRecording():
            raise ValueError('Cannot set filename while logger is running.')
        self._filename = filename
        self.fileNameChanged.emit(self._filename)

    def fileName(self) -> str:
        return self._filename

    def period(self) -> float:
        return self._period

    def setPeriod(self, period: float):
        if self.isRecording():
            raise ValueError('Cannot set period while logger is running.')
        self._period = period
        self.periodChanged.emit(self._period)

    def name(self) -> str:
        return self._name

    def setName(self, name: str):
        if self.isRecording():
            raise ValueError('Cannot set name while logger is running.')
        self._name = name
        self.nameChanged.emit(self._name)

    def nrecord(self) -> int:
        return self._nrecord

    def setNrecord(self, nrecord: int):
        if self.isRecording():
            raise ValueError('Cannot set nrecord while logger is running.')
        self._nrecord = nrecord
        self.nrecordChanged.emit(self._nrecord)

    def addRecordedVariable(self, devicename: str, variablename: str, scaling: float = 1.0, vartype: Optional[VariableType]=None):
        if vartype is None:
            dev: DeviceFrontend = self._devicemanager[devicename]
            var: Variable = dev.getVariable(variablename)
            vartype = var.vartype
        if vartype in [VariableType.FLOAT,
                           VariableType.INT, VariableType.BOOL]:
            self.beginInsertRows(QtCore.QModelIndex(), len(self._variables), len(self._variables))
            self._variables.append(RecordedVariable(devicename, variablename, vartype, scaling))
            self.endInsertRows()
        else:
            raise ValueError(f'Cannot record variable of type {vartype.name}')

    @Slot(str, object, object)
    def onVariableChanged(self, name: str, newvalue: Any, oldvalue: Any):
        device = self.sender()
        devname = device.name
        if [v for v in self._variables if v.devicename == devname and v.variablename == name]:
            self.recordCurrentValues()

    def recordCurrentValues(self) -> Optional[Tuple[Any, ...]]:
        if not self.isRecording():
            return None
        try:
            self._record[self._recordpointer]['Time'] = time.time()
            for v in self._variables:
                try:
                    val = self._devicemanager[v.devicename][v.variablename]
                except (KeyError, DeviceFrontend.DeviceError):
                    val = None
                if val is None:
                    self._record[self._recordpointer][v.devicename + '/' + v.variablename] = npma.masked
                else:
                    if v.vartype == VariableType.FLOAT:
                        self._record[self._recordpointer][v.devicename + '/' + v.variablename] = val * v.scaling
                    elif v.vartype == VariableType.BOOL:
                        self._record[self._recordpointer][v.devicename + '/' + v.variablename] = val
                    elif v.vartype == VariableType.INT:
                        self._record[self._recordpointer][v.devicename + '/' + v.variablename] = int(val*v.scaling)
                    else:
                        assert False
            return tuple([x if x is not npma.masked else None for x in self._record[self._recordpointer]])
        finally:
            nextptr = (self._recordpointer + 1) % self._nrecord
            if nextptr == self._savepointer:
                # the next record will overwrite an unsaved one. Flush the record to disk!
                self.writeRecord()
            self._recordpointer = nextptr
            self.newData.emit(self._recordpointer)

    def timerEvent(self, a0: QtCore.QTimerEvent) -> None:
        if a0.timerId() == self._recordtimerhandle:
            self.recordCurrentValues()
        elif a0.timerId() == self._writetimerhandle:
            self.writeRecord()

    def writeRecord(self):
        if (self._filename is None) or (not self._filename):
            self._savepointer = self._recordpointer  # emulate that the data has been saved
            return
        if not os.path.exists(self._filename):
            try:
                with open(self._filename, 'wt') as f:
                    f.write('# ' + '  '.join(self._record.dtype.names) + '\n')
            except FileNotFoundError:
                # path does not exist:
                return
        with open(self._filename, 'at') as f:
            # watch out for the cyclic buffer!
            if self._savepointer < self._recordpointer:
                # the record pointer did not yet wrap
                np.savetxt(f, self._record[self._savepointer:self._recordpointer])
                self._savepointer = self._recordpointer
            elif self._savepointer > self._recordpointer:
                # the record pointer wrapped after the last save: save the data until the end of the buffer, then wrap
                # around and save the rest.
                np.savetxt(f, self._record[self._savepointer:])
                self._savepointer = 0
                self.writeRecord()  # now self._savepointer is <= self._recordpointer
            else:
                assert self._savepointer == self._recordpointer
                # nothing to do

    def record(self) -> Optional[npma.masked_array]:
        return self._record

    def __len__(self):
        return len(self._variables)

    def variables(self) -> List[Tuple[str, str, str, float]]:
        return [(v.devicename, v.variablename, v.vartype.name, v.scaling) for v in self._variables]