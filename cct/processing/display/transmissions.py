import h5py
from PyQt5 import QtCore
from sastool.misc.errorvalue import ErrorValue


class TransmissionModel(QtCore.QAbstractItemModel):
    # columns: sample, distance, thickness, transmission, mu, 1/mu

    def __init__(self, parent, group: h5py.Group):
        super().__init__(parent)
        self._data = []
        for sn in sorted(group.keys()):
            for dist in sorted(group[sn].keys(), key=float):
                if 'curves' not in group[sn][dist]:
                    continue
                for c in group[sn][dist]['curves'].keys():
                    dset = group[sn][dist]['curves'][c]
                    res = (sn, float(dist), dset.attrs['transmission'], dset.attrs['transmission.err'],
                           dset.attrs['thickness'], dset.attrs['thickness.err'])
                    if res not in self._data:
                        self._data.append(res)

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 6

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._data)

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        thickness = ErrorValue(self._data[index.row()][4], self._data[index.row()][5])
        transm = ErrorValue(self._data[index.row()][2], self._data[index.row()][3])
        if role != QtCore.Qt.DisplayRole:
            return None
        if index.column() == 0:  # sample name
            return self._data[index.row()][0]
        elif index.column() == 1:  # distance
            return '{:.2f}'.format(self._data[index.row()][1])
        elif index.column() == 2:  # thickness
            return thickness.tostring(plusminus=' \xb1 ')
        elif index.column() == 3:  # transmission
            return transm.tostring(plusminus=' \xb1 ')
        elif index.column() == 4:  # mu
            if transm.val > 0 and transm.val <1:
                return (-transm.log() / thickness).tostring(plusminus=' \xb1 ')
            elif transm.val>=1:
                return '0'
            else:
                return '\u221e'  # infinity
        elif index.column() == 5:  # 1/mu
            if abs(transm.val-1)<0.0001:
                return '\u221e'  # infinity
            elif transm.val < 0.0001:
                return '0'
            else:
                return (-thickness / transm.log()).tostring(plusminus=' \xb1 ')

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Sample', 'Distance (cm)', 'Thickness (cm)', 'Transmission', 'Lin. abs. coeff (1/cm)',
                    'Absorption length (cm)'][section]
        return None

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled


def make_transmission_table(grp: h5py.Group):
    model = TransmissionModel(None, group=grp)
    return model
