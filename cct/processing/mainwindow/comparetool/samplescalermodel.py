import typing

from PyQt5 import QtCore


class SampleScalerModel(QtCore.QAbstractItemModel):
    def __init__(self, samples: typing.List[str]):
        super().__init__(None)
        self._samples = samples[:]
        self._factors = dict(zip(self._samples, [1.0] * len(self._samples)))
        self._selected = dict(zip(self._samples, [True] * len(self._samples)))

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return self._samples[index.row()]
            elif index.column() == 1:
                return str(self.factorForSample(self._samples[index.row()]))
        elif role == QtCore.Qt.CheckStateRole:
            if index.column() == 0:
                return [QtCore.Qt.Unchecked, QtCore.Qt.Checked][self._samples[index.row()] in self.selectedSamples()]
        elif role == QtCore.Qt.EditRole:
            if index.column() == 1:
                return self.factorForSample(self._samples[index.row()])
        return None

    def flags(self, index: QtCore.QModelIndex):
        if index.column() == 0:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren
        elif index.column() == 1:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemNeverHasChildren

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 2

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._samples)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Sample', 'Scaling factor'][section]

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = ...):
        if index.column() == 1 and role == QtCore.Qt.EditRole:
            self._factors[self._samples[index.row()]] = value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), index.column()),
                                  [QtCore.Qt.DisplayRole])
            return True
        elif index.column() == 0 and role == QtCore.Qt.CheckStateRole:
            self._selected[self._samples[index.row()]] = value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), index.column()),
                                  [QtCore.Qt.DisplayRole, QtCore.Qt.CheckStateRole])
        return False

    def selectedSamples(self):
        return [s for s in self._samples if self._selected[s]]

    def factorForSample(self, samplename: str):
        return self._factors[samplename]

    def selectAll(self):
        for sn in self._selected:
            self._selected[sn] = True
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount(), 0), [QtCore.Qt.CheckStateRole])

    def deselectAll(self):
        for sn in self._selected:
            self._selected[sn] = False
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount(), 0), [QtCore.Qt.CheckStateRole])
