from PyQt5 import QtCore


class SignalModel(QtCore.QAbstractItemModel):
    signals_invisible_by_default=['FSN','epoch']

    def __init__(self, signals, parent=None):
        super().__init__(parent)
        self._signaldata = [list(x) for x in list(zip(signals, [1.0] * len(signals), [True] * len(signals)))]
        for signal in self._signaldata:
            if signal[0] in self.signals_invisible_by_default:
                signal[2]=False

    def columnCount(self, parent=None, *args, **kwargs):
        return 2

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._signaldata)

    def data(self, index: QtCore.QModelIndex, role=None):
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return self._signaldata[index.row()][0]
            elif index.column() == 1:
                return self._signaldata[index.row()][1]
            else:
                assert False
        elif role == QtCore.Qt.CheckStateRole and index.column() == 0:
            return [QtCore.Qt.Unchecked, QtCore.Qt.Checked][self._signaldata[index.row()][2]]
        elif role == QtCore.Qt.EditRole and index.column() == 1:
            print('EditRole requested from row {}'.format(index.row()))
            return float(self._signaldata[index.row()][1])
        return None

    def flags(self, index: QtCore.QModelIndex):
        flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled
        if index.column() == 0:
            flags |= QtCore.Qt.ItemIsUserCheckable
        elif index.column() == 1:
            flags |= QtCore.Qt.ItemIsEditable
        return flags

    def index(self, p_int, p_int_1, parent=None, *args, **kwargs):
        return self.createIndex(p_int, p_int_1, None)

    def headerData(self, column: int, orientation, role=None):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Signal', 'Scaling'][column]

    def setData(self, index: QtCore.QModelIndex, value, role=None):
        print('SetData: row {}, column {}, role {}'.format(index.row(), index.column(), role))
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            self._signaldata[index.row()][2] = bool(value)
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), 0))
            return True
        elif role == QtCore.Qt.EditRole and index.column() == 1:
            self._signaldata[index.row()][1] = value
            self.dataChanged.emit(self.index(index.row(), 1), self.index(index.row(), 1))
            return True
        return False

    def names(self):
        return [sd[0] for sd in self._signaldata]

    def factor(self, name):
        return [sd[1] for sd in self._signaldata if sd[0] == name][0]

    def visible(self, name):
        return [sd[2] for sd in self._signaldata if sd[0] == name][0]

    def parent(self, idx: QtCore.QModelIndex = None):
        return QtCore.QModelIndex()

    def setVisible(self, name, state):
        if name is None:
            for sd in self._signaldata:
                sd[2] = state
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, 0))
        else:
            for i, sd in enumerate(self._signaldata):
                if sd[0] == name:
                    sd[2] = state
                    self.dataChanged.emit(self.index(i, 0), self.index(i, 0))
