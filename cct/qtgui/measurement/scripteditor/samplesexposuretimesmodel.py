import typing

from PyQt5 import QtCore


class ExposureTimesModel(QtCore.QAbstractItemModel):
    def __init__(self, parent=None, default_exptime=300, default_iterations = 1):
        super().__init__(parent)
        self._samples={}
        self.default_exptime = default_exptime
        self.default_iterations = default_iterations

    def addSample(self, samplename):
        if samplename not in self._samples:
            self.beginResetModel()
            self._samples[samplename] = [False, self.default_exptime, self.default_iterations]
            self.endResetModel()

    def removeSample(self, samplename):
        if samplename in self._samples:
            self.beginResetModel()
            del self._samples[samplename]
            self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._samples)

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 3

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        samplename = sorted(self._samples.keys())[index.row()]
        if index.column()==0:
            if role == QtCore.Qt.CheckStateRole:
                return [QtCore.Qt.Unchecked, QtCore.Qt.Checked][self._samples[samplename][0]]
            elif role == QtCore.Qt.DisplayRole:
                return samplename
            else:
                return None
        else:
            if role == QtCore.Qt.DisplayRole:
                return str(self._samples[samplename][index.column()])
            elif role == QtCore.Qt.EditRole:
                return self._samples[samplename][index.column()]
            else:
                return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Sample name', 'Exposure time', 'Iterations'][section]
        return None

    def flags(self, index: QtCore.QModelIndex):
        samplename = sorted(self._samples.keys())[index.row()]
        flags = QtCore.Qt.ItemNeverHasChildren
        if index.column()==0:
            flags |= QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled
        else:
            flags |= QtCore.Qt.ItemIsEditable
            if self._samples[samplename][0]:
                flags |= QtCore.Qt.ItemIsEnabled
        return flags

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = ...):
        samplename = sorted(self._samples.keys())[index.row()]
        if role == QtCore.Qt.EditRole:
            assert isinstance(value, (float, int))
            self._samples[samplename][index.column()] = value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), index.column()))
            return True
        elif role == QtCore.Qt.CheckStateRole:
            assert index.column()==0
            self._samples[samplename][0]=value>0
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), 3))
            return True
        return False

    def __contains__(self, samplename):
        return samplename in self._samples

    def __iter__(self):
        for sam in sorted(self._samples):
            if self._samples[sam][0]:
                yield sam, self._samples[sam][1], self._samples[sam][2]
        return