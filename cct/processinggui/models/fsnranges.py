import typing

from PyQt5 import QtCore, QtGui


class FSNRangeModel(QtCore.QAbstractItemModel):
    _columnnames = ['Start', 'End']
    _data = typing.List[typing.Tuple[int, int]]

    def __init__(self, data:typing.Optional[typing.List[typing.Tuple[int, int]]] = None):
        super().__init__()
        self._data = data if data is not None else []

    def rowCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex)  and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._columnnames)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        if role == QtCore.Qt.DisplayRole:
            return str(self._data[index.row()][index.column()])
        elif role == QtCore.Qt.BackgroundColorRole:
            if self._data[index.row()][0]>self._data[index.row()][1]:
                return QtGui.QColor('orange')
            else:
                return None
        elif role == QtCore.Qt.DecorationRole:
            if self._data[index.row()][0] > self._data[index.row()][1]:
                return QtGui.QIcon.fromTheme('dialog-warning')
        return None

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = None) -> bool:
        if role == QtCore.Qt.EditRole:
            if index.column() == 0:
                try:
                    self._data[index.row()] = (int(value), self._data[index.row()][1])
                except ValueError:
                    return False
            else:
                assert index.column() == 1
                try:
                    self._data[index.row()] = (self._data[index.row()][0], int(value))
                except ValueError:
                    return False
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount()),
                                  [QtCore.Qt.DisplayRole, QtCore.Qt.BackgroundColorRole, QtCore.Qt.DecorationRole])
            return True
        return False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        # edit this to your needs
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEditable

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._columnnames[section]
        return None

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = None) -> QtCore.QModelIndex:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return self.createIndex(row, column, None)

    def removeRow(self, row: int, parent: QtCore.QModelIndex = None) -> bool:
        return self.removeRows(row, 1, parent)

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = None) -> bool:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        self.beginRemoveRows(QtCore.QModelIndex(), row, row + count)
        for i in reversed(range(row, row + count)):
            del self._data[i]
        self.endRemoveRows()
        return True

    def add(self, fsnmin:int, fsnmax:int):
        # edit this to your needs
        self.beginInsertRows(QtCore.QModelIndex(), self.rowCount(), self.rowCount() + 1)
        self._data.append((fsnmin, fsnmax))
        self.endInsertRows()

    def toList(self) -> typing.List[typing.Tuple[int, int]]:
        return self._data[:] # return a copy for safety

    def fromList(self, lis: typing.List[typing.Tuple[int, int]]):
        self.beginResetModel()
        self._data = lis[:]
        self.endResetModel()

    def fsns(self) -> typing.List[int]:
        lis=[]
        for start, end in self._data:
            lis.extend(list(range(min(start,end), max(start,end)+1)))
        return lis