from typing import Any, List
import logging

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Slot

from .devicestatuslogger import DeviceStatusLogger
from ....devices.device.variable import VariableType
from ..component import Component

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DeviceLogManager(Component, QtCore.QAbstractItemModel):
    _loggers: List[DeviceStatusLogger]

    def __init__(self, **kwargs):
        self._loggers = []
        super().__init__(**kwargs)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._loggers)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 5

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        lgr = self._loggers[index.row()]
        if (index.column() == 0) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return lgr.name()
        elif (index.column() == 1) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return lgr.fileName()
        elif (index.column() == 2) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return f'{len(lgr)}'
        elif (index.column() == 3) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return f'{lgr.period()}'
        elif (index.column() == 4) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return 'Running' if lgr.isRecording() else 'Stopped'
        elif (index.column() == 4) and (role == QtCore.Qt.ItemDataRole.DecorationRole):
            return QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg' if lgr.isRecording() else ':/icons/stop.svg'))
        elif (index.column() == 0) and (role == QtCore.Qt.ItemDataRole.EditRole):
            return lgr.name()
        elif (index.column() == 1) and (role == QtCore.Qt.ItemDataRole.EditRole):
            return lgr.fileName()
        elif (index.column() == 2) and (role == QtCore.Qt.ItemDataRole.EditRole):
            return None
        elif (index.column() == 3) and (role == QtCore.Qt.ItemDataRole.EditRole):
            return lgr.period()
        elif (index.column() == 4) and (role == QtCore.Qt.ItemDataRole.EditRole):
            return lgr.isRecording()
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        lgr = self._loggers[index.row()]
        if (index.column() == 0) and (role == QtCore.Qt.ItemDataRole.EditRole):
            lgr.setName(value)
            self.dataChanged.emit(index, index)
            self.saveToConfig()
            return True
        if (index.column() == 1) and (role == QtCore.Qt.ItemDataRole.EditRole):
            lgr.setFileName(value)
            self.dataChanged.emit(index, index)
            self.saveToConfig()
            return True
        elif (index.column() == 3) and (role == QtCore.Qt.ItemDataRole.EditRole):
            try:
                lgr.setPeriod(float(value))
            except ValueError:
                return False
            self.dataChanged.emit(index, index)
            self.saveToConfig()
            return True
        elif (index.column() == 4) and (role == QtCore.Qt.ItemDataRole.EditRole):
            if value:
                lgr.startRecording()
            else:
                lgr.stopRecording()
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if (index.column() in [0, 1, 3]) and not self._loggers[index.row()].isRecording():
            return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEditable
        elif index.column() == 4:
            return QtCore.Qt.ItemFlag.ItemIsEditable | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEnabled
        else:
            return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemNeverHasChildren

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginRemoveRows(parent, row, row + count - 1)
        for lgr in self._loggers[row:row+count]:
            try:
                lgr.deleteLater()
            except RuntimeError:
                pass
        del self._loggers[row:row + count]
        self.endRemoveRows()
        self.saveToConfig()
        return True

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.removeRows(row, 1, parent)

    def insertRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginInsertRows(parent, row, row+count-1)
        for i in range(count):
            nameindex = 1
            while (name := f'Untitled_{nameindex}') in [lgr.name() for lgr in self._loggers]:
                nameindex += 1
            lgr = DeviceStatusLogger(self.instrument.devicemanager, name=name)
            lgr.rowsInserted.connect(self.saveToConfig)
            lgr.rowsRemoved.connect(self.saveToConfig)
            lgr.modelReset.connect(self.saveToConfig)
            lgr.destroyed.connect(self.onLoggerDestroyed)
            self._loggers.insert(row+i, lgr)
        self.endInsertRows()
        self.saveToConfig()
        return True

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.insertRows(row, 1, parent)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (role == QtCore.Qt.ItemDataRole.DisplayRole) and (orientation == QtCore.Qt.Orientation.Horizontal):
            return ['Name', 'File name', 'Variable count', 'Period', 'Running?'][section]

    def loadFromConfig(self):
        if 'deviceloggers' not in self.config:
            self.config['deviceloggers'] = {}
        self.beginResetModel()
        try:
            self._loggers = []
            for loggerkey in sorted(self.config['deviceloggers']):
                lgr = DeviceStatusLogger(
                    self.instrument.devicemanager,
                    self.config['deviceloggers'][loggerkey]['filename'],
                    float(self.config['deviceloggers'][loggerkey]['period']), loggerkey)
                for devname, varname, vartype, scaling in self.config['deviceloggers'][loggerkey]['variables']:
                    lgr.addRecordedVariable(devname, varname, scaling, vartype=VariableType[vartype])
                lgr.rowsInserted.connect(self.saveToConfig)
                lgr.rowsRemoved.connect(self.saveToConfig)
                lgr.modelReset.connect(self.saveToConfig)
                lgr.destroyed.connect(self.onLoggerDestroyed)
                self._loggers.append(lgr)
        finally:
            self.endResetModel()

    @Slot()
    def saveToConfig(self):
        try:
            self.config.objectName()
        except RuntimeError:
            # this happens sometimes at shutdown, when the log manager is notified too late on the destroying of a
            # device logger.
            return
        self.config['deviceloggers'] = {}
        for key in list(self.config['deviceloggers'].keys()):
            # Config is somewhat counterintuitive here, assigning a {} does not make it empty, only updates it
            del self.config['deviceloggers'][key]
        for i, lgr in enumerate(self._loggers):
            logger.debug(f'Saving logger {lgr.name()}')
            self.config['deviceloggers'][lgr.name()] = {
                'filename': lgr.fileName(),
                'period': lgr.period(),
                'variables': lgr.variables(),
            }
        logger.debug(f'Loggers saved to config: {self.config["deviceloggers"].keys()}')

    def startAll(self):
        for lgr in self._loggers:
            if not lgr.isRecording():
                lgr.startRecording()

    def stopAll(self):
        for lgr in self._loggers:
            if lgr.isRecording():
                lgr.stopRecording()

    def startComponent(self):
        self.startAll()
        super().startComponent()

    def stopComponent(self):
        self.stopAll()
        return super().stopComponent()

    def __getitem__(self, item: int) -> DeviceStatusLogger:
        return self._loggers[item]

    def __len__(self) -> int:
        return len(self._loggers)

    @Slot(QtCore.QObject, name = 'onLoggerDestroyed')
    def onLoggerDestroyed(self, object: QtCore.QObject):
        logger.debug(f'Logger {object.objectName()} has been destroyed.')
        while True:
            for i, lgr in enumerate(self._loggers[:]):
                try:
                    if lgr.objectName() == object.objectName():
                        self.removeRow(i, QtCore.QModelIndex())
                    continue
                except RuntimeError:
                    logger.warning(f'Found a stale device logger handle at row {i}')
                    self.removeRow(i, QtCore.QModelIndex())
                    break
            else:
                break