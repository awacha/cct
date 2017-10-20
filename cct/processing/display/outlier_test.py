import h5py
from PyQt5 import QtCore

class OutlierModel(QtCore.QAbstractItemModel):
    def __init__(self, parent, group:h5py.Group):
        super().__init__(parent)
        self._data=[]
        sortedkeys = sorted(group.keys(), key=lambda x:int(x))
        for fsn in sortedkeys:
            dset=group[fsn]
            self._data.append([
                int(fsn), dset.attrs['date'], dset.attrs['correlmat_discrp'],
                dset.attrs['correlmat_rel_discrp'],
                ['Good','BAD'][dset.attrs['correlmat_bad']]])

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 5

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._data)

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role==QtCore.Qt.DisplayRole:
            return str(self._data[index.row()][index.column()])
        else:
            return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if role!=QtCore.Qt.DisplayRole:
            return None
        if orientation==QtCore.Qt.Horizontal:
            return ['FSN','Date','Discrepancy','Relative discrepancy', 'Quality'][section]
        else:
            return None

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def getFSN(self, index:QtCore.QModelIndex):
        return self._data[index.row()][0]

def display_outlier_test_results(grp:h5py.Group) -> OutlierModel:
    return OutlierModel(None, grp)