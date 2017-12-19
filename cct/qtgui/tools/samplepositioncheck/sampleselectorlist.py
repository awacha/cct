import typing

from PyQt5 import QtCore

from ....core.instrument.instrument import Instrument
from ....core.services.samples import SampleStore


class SampleSelectorModel(QtCore.QAbstractItemModel):
    def __init__(self, credo: Instrument):
        super().__init__(None)
        self.credo = credo
        self._samples = {}
        self.update()

    def columnCount(self, parent: QtCore.QModelIndex = None):
        return 1

    def rowCount(self, parent: QtCore.QModelIndex = None):
        return len(self._samples)

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = None):
        if parent is None or parent.isValid():
            return QtCore.QModelIndex()
        else:
            return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsUserCheckable

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole and section == 0:
            return 'Sample name'
        return None

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole:
            return list(sorted(self._samples))[index.row()]
        elif role == QtCore.Qt.CheckStateRole:
            return self._samples[list(sorted(self._samples))[index.row()]]
        else:
            return None

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = QtCore.Qt.DisplayRole):
        sn = list(sorted(self._samples))[index.row()]
        if role == QtCore.Qt.CheckStateRole:
            self._samples[sn] = value
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def update(self):
        self.beginResetModel()
        ss = self.credo.services['samplestore']
        assert isinstance(ss, SampleStore)
        for x in ss:
            if x.title not in self._samples:
                self._samples[x.title] = False
        for x in list(self._samples):
            if x not in ss:
                del self._samples[x]
        self.endResetModel()

    def getSelected(self):
        return sorted([s for s in self._samples if self._samples[s]])

    def setSelected(self, lis):
        for sn in self._samples:
            self._samples[sn]=sn in lis
        self.dataChanged.emit(self.index(0,0), self.index(self.rowCount(),0), [QtCore.Qt.CheckStateRole])