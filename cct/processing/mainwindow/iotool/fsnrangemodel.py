from PyQt5 import QtCore
from typing import List, Tuple, Any

class FSNRangeModel(QtCore.QAbstractItemModel):
    _ranges:List[Tuple[int,int]]
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ranges=[]

    def addRange(self, minimum:int, maximum:int):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._ranges), len(self._ranges))
        self._ranges.append((min(minimum, maximum), max(minimum, maximum)))
        self.endInsertRows()

    def removeRow(self, row:int, parent:QtCore.QModelIndex=...):
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._ranges[row]
        self.endRemoveRows()

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 2

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._ranges)

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.DisplayRole:
            return str(self._ranges[index.row()][index.column()])
        elif role == QtCore.Qt.EditRole:
            return self._ranges[index.row()][index.column()]
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...):
        if role == QtCore.Qt.EditRole:
            lis = list(self._ranges[index.row()])
            lis[index.column()] = value
            self._ranges[index.row()]=(min(lis), max(lis))
            self.dataChanged.emit(self.index(index.row(),0), self.index(index.row(),1), [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
            return True
        return False

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemNeverHasChildren

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation==QtCore.Qt.Horizontal and role==QtCore.Qt.DisplayRole:
            return ['Minimum', 'Maximum'][section]

    def getRanges(self):
        return self._ranges[:]

    def getFSNs(self):
        return sum([list(range(left,right+1)) for left, right in self._ranges])

    def clear(self):
        self.beginResetModel()
        self._ranges=[]
        self.endResetModel()