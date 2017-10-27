import h5py
from PyQt5 import QtCore


class ExpTimeModel(QtCore.QAbstractItemModel):
    # columns: sample, distance, exposure time (hours), exptime percent, number of exposures, avg. exptime

    def __init__(self, parent, group: h5py.Group):
        super().__init__(parent)
        self._data = []
        for sn in sorted(group.keys()):
            for dist in sorted(group[sn].keys(), key=float):
                self._data.append(
                    (sn, float(dist), group[sn][dist].attrs['exposuretime'], len(group[sn][dist]['curves'])))

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 6

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._data)+1

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role != QtCore.Qt.DisplayRole:
            return None
        if index.row() == len(self._data):
            if index.column() == 0: # sample name
                return '-- Total --'
            elif index.column() == 4: # exptime
                return '{:.2f}'.format(sum([d[2] for d in self._data])/3600.)
            elif index.column() == 5: # exptime pcnt
                return '100 %'
            else:
                return ''
        else:
            if index.column() == 0:  # sample name
                return self._data[index.row()][0]
            elif index.column() == 1:  # distance
                return '{:.2f}'.format(self._data[index.row()][1])
            elif index.column() == 2:  # nr. of exposures
                return '{}'.format(self._data[index.row()][3])
            elif index.column() == 3:  # avg. exptime
                return '{:.2f}'.format(self._data[index.row()][2] / self._data[index.row()][3])
            elif index.column() == 4:  # exptime
                return '{:.2f}'.format(self._data[index.row()][2] / 3600.)
            elif index.column() == 5:  # exptime pcnt
                return '{:.2f} %'.format(100 * self._data[index.row()][2] / sum(d[2] for d in self._data))

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Sample', 'Distance (cm)', '# of exposures', 'Frame time (sec)', 'Live time (h)', 'Rel. live time'][
                section]
        return None

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled


def make_exptimes_table(group: h5py.Group):
    return ExpTimeModel(None, group)
