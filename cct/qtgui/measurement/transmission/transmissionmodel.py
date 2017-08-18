import weakref

from PyQt5 import QtCore
from sastool.misc.errorvalue import ErrorValue


class TransmissionModel(QtCore.QAbstractItemModel):
    def __init__(self, parent, credo):
        super().__init__()
        try:
            self.credo = weakref.proxy(credo)
        except TypeError:
            self.credo = credo
        self._samples = []

    def add_sample(self, samplename):
        if samplename not in self:
            self.beginInsertRows(QtCore.QModelIndex(), len(self._samples), len(self._samples) + 1)
            self._samples.append([samplename, None, None, None, None])
            self.endInsertRows()

    def _update_intensityvalue(self, samplename, value, i, j=None):
        [s for s in self._samples if s[0] == samplename][0][i] = value
        s = [s_ for s_ in self._samples if s_[0] == samplename][0]
        row = self._samples.index(s)
        if j is None:
            j = i
        self.dataChanged.emit(self.createIndex(row, i), self.createIndex(row, j))

    def update_dark(self, samplename, value):
        return self._update_intensityvalue(samplename, value, 1)

    def update_empty(self, samplename, value):
        return self._update_intensityvalue(samplename, value, 2)

    def update_sample(self, samplename, value):
        return self._update_intensityvalue(samplename, value, 3)

    def update_transm(self, samplename, value):
        return self._update_intensityvalue(samplename, value, 4, 7)

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = None):
        return self.createIndex(row, column, None)

    def columnCount(self, parent: QtCore.QModelIndex = None):
        return 7

    def rowCount(self, parent: QtCore.QModelIndex = None):
        return len(self._samples)

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return
        if index.column() == 0:
            return self._samples[index.row()][0]
        elif index.column() in [1, 2, 3, 4]:
            val = self._samples[index.row()][index.column()]
            if val is None:
                val = '--'
            else:
                assert isinstance(val, ErrorValue)
                val = val.tostring(plusminus=' \xb1 ')
            return val
        elif index.column() in [5, 6]:
            thickness = self.credo.services['samplestore'].get_sample(self._samples[index.row()][0]).thickness
            transm = self._samples[index.row()][4]
            if transm is None:
                return '--'
            assert isinstance(transm, ErrorValue)
            assert isinstance(thickness, ErrorValue)
            mu = - transm.log() / thickness
            if index.column() == 5:
                return mu.tostring(plusminus=' \xb1 ')
            else:
                return (1 / mu).tostring(plusminus=' \xb1 ')
        else:
            return None

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole):
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return \
            ['Name', 'Dark intensity', 'Empty intensity', 'Sample intensity', 'Transmission', 'Lin.abs.coeff (1/cm)',
             'Absorption length (cm)'][section]
        else:
            return None

    def __contains__(self, item):
        return item in [s[0] for s in self._samples]

    def samplenames(self):
        return [s[0] for s in self._samples]
