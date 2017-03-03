from PyQt5 import QtCore


class PairStore(QtCore.QAbstractItemModel):
    def __init__(self, *args, **kwargs):
        QtCore.QAbstractItemModel.__init__(self, *args, **kwargs)
        self._pairs = []

    def columnCount(self, parent=None, *args, **kwargs):
        return 2

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._pairs)

    def parent(self, index:QtCore.QModelIndex=None):
        return QtCore.QModelIndex()

    def data(self, index:QtCore.QModelIndex, role=None):
        if role == QtCore.Qt.DisplayRole:
            return str(self._pairs[index.row()][index.column()])
        else:
            return None

    def index(self, row:int, column:int, parent:QtCore.QModelIndex):
        return self.createIndex(row, column, None)

    def addPair(self, uncalibrated, calibrated):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._pairs), len(self._pairs)+1)
        self._pairs.append((uncalibrated, calibrated))
        self.endInsertRows()

    def removePair(self, row):
        self.beginRemoveRows(QtCore.QModelIndex(), row, row+1)
        del self._pairs[row]
        self.endRemoveRows()

    def flags(self, index:QtCore.QModelIndex):
        return QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren

    def pairs(self):
        return self._pairs[:]

    def headerData(self, column, orientation, role=None):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return ['Uncalibrated (pixel)', 'Calibrated (q)'][column]
