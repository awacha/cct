import datetime
import typing

import numpy as np
from PyQt5 import QtCore, QtGui


class OutlierTestResult:
    fsn: int
    date: datetime.datetime
    score: float
    stdscore: float
    verdict: str

    def __init__(self, fsn: int, date: datetime.datetime, score: float, stdscore: float, verdict: str):
        self.fsn = fsn
        self.date = date
        self.score = score
        self.stdscore = stdscore
        self.verdict = verdict

    def isBad(self) -> bool:
        return self.verdict.upper() not in ['GOOD']


class OutlierTestResults(QtCore.QAbstractItemModel):
    _columnnames = ['FSN', 'Date', 'Score', 'Std.score', 'Verdict']  # fill this
    _data: typing.List[OutlierTestResult]

    def __init__(self):
        super().__init__()
        self._data = []

    def rowCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._columnnames)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return '{}'.format(self._data[index.row()].fsn)
            elif index.column() == 1:
                return '{:%Y-%m-%d %H:%M:%S}'.format(self._data[index.row()].date)
            elif index.column() == 2:
                return '{:.6f}'.format(self._data[index.row()].score) if np.isfinite(self._data[index.row()].score) else '--'
            elif index.column() == 3:
                return '{:.3f}'.format(self._data[index.row()].stdscore) if np.isfinite(self._data[index.row()].stdscore) else '--'
            elif index.column() == 4:
                return self._data[index.row()].verdict
        elif role == QtCore.Qt.BackgroundRole:
            if self._data[index.row()].isBad():
                return QtGui.QBrush(QtGui.QColor('red'))
        return None

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = None) -> bool:
        # edit this to your needs
        return False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        # edit this to your needs
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren

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

    def setValues(self, fsns: typing.Sequence[int], dates: typing.Sequence[datetime.datetime],
                  scores: typing.Sequence[float], verdicts: typing.Sequence[str]):
        stdscores = (np.array(scores) - np.nanmean(scores)) / np.nanstd(scores)
        self.beginResetModel()
        self._data = [OutlierTestResult(f, d, s, ss, v) for f, d, s, ss, v in
                      zip(fsns, dates, scores, stdscores, verdicts)]
        self.endResetModel()

    def __getitem__(self, item) -> OutlierTestResult:
        return self._data[item]