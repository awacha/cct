from typing import Dict, Any, Iterable

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot


class InterpreterFlags(QtCore.QAbstractItemModel):
    _flags: Dict[str, bool]
    newFlag = Signal(str, bool)
    flagChanged = Signal(str, bool)
    flagRemoved = Signal(str)

    def __init__(self):
        super().__init__()
        self._flags={}

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        flag = sorted(self._flags.keys())[index.row()]
        if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
            return flag
        elif (index.column() == 0) and (role == QtCore.Qt.CheckStateRole):
            return QtCore.Qt.Checked if self._flags[flag] else QtCore.Qt.Unchecked
        return False

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._flags)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 1

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Flag'][section]

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if role == QtCore.Qt.CheckStateRole:
            flag = sorted(self._flags)[index.row()]
            self._flags[flag] = True if value == QtCore.Qt.Checked else False
            self.dataChanged.emit(index, index, [QtCore.Qt.CheckStateRole])
            return True
        else:
            return False

    def addFlag(self, flagname: str, state: bool):
        if flagname in self._flags:
            raise ValueError(f'Flag {flagname} already exists')
        else:
            self.beginResetModel()
            self._flags[flagname] = state
            self.endResetModel()
            self.newFlag.emit(flagname, state)

    def removeFlag(self, flagname: str):
        if flagname not in self._flags:
            raise KeyError(f'Flag {flagname} does not exist.')
        else:
            self.beginResetModel()
            del self._flags[flagname]
            self.endResetModel()
            self.flagRemoved.emit(flagname)

    def setFlag(self, flagname: str, state: bool):
        if flagname not in self._flags:
            raise KeyError(f'Flag {flagname} does not exist.')
        else:
            self._flags[flagname] = state
            row = sorted(self._flags).index(flagname)
            self.dataChanged.emit(
                self.index(row, 0, QtCore.QModelIndex()),
                self.index(row, 0, QtCore.QModelIndex()), [QtCore.Qt.CheckStateRole])
            self.flagChanged.emit(flagname, state)

    def __len__(self) -> int:
        return len(self._flags)

    def __iter__(self) -> Iterable[str]:
        return iter(sorted(self._flags))

    def __contains__(self, item):
        return item in self._flags

    def __getitem__(self, item):
        return self._flags[item]

    def __setitem__(self, key, value):
        self.setFlag(key, value)

    def __delitem__(self, key):
        return self.removeFlag(key)

    def reset(self):
        for flag in list(self._flags):
            self.removeFlag(flag)
