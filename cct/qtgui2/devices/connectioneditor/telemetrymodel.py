from typing import Optional, Any

from PyQt5 import QtCore
from ....core2.devices.device.telemetry import TelemetryInformation


class TelemetryModel(QtCore.QAbstractItemModel):
    _telemetry: Optional[TelemetryInformation] = None

    def __init__(self):
        super().__init__()
        self._telemetry = None

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        if self._telemetry is None:
            return 0
        return len(self._telemetry.attributeinfo)
    
    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 2
    
    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()
    
    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEnabled
    
    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, parent)
    
    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if self._telemetry is None:
            return None
        if (role == QtCore.Qt.ItemDataRole.DisplayRole) and index.column() == 0:
            return self._telemetry.attributeinfo[index.row()].description
        elif (role == QtCore.Qt.ItemDataRole.DisplayRole) and index.column() == 1:
            return self._telemetry.attributeinfo[index.row()].formatter(getattr(self._telemetry, self._telemetry.attributeinfo[index.row()].name))
        else:
            return None

    
    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Orientation.Horizontal) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return ['Quantity', 'Value'][section]
        else:
            return None
    
    def setTelemetry(self, telemetry: TelemetryInformation):
        self.beginResetModel()
        self._telemetry = telemetry
        self.endResetModel()
