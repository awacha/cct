import typing

import numpy as np
from PyQt5 import QtCore
from sastool.misc.easylsq import nonlinear_leastsquares
from sastool.misc.errorvalue import ErrorValue


class PeakModel(QtCore.QAbstractItemModel):
    # columns: q, h, k, l, lattice parameter, s-d dist
    calibrationChanged = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self._peaks=[]

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 6

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._peaks)

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex):
        flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable
        if index.column() in [1,2,3]:
            flags |= QtCore.Qt.ItemIsEditable
        return flags

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.DisplayRole:
            if index.column() in [0, 5]:
                return '{0.val:.4f} \xb1 {0.err:.4f}'.format(self._peaks[index.row()][index.column()])
            elif index.column() in [1,2,3]:
                return str(self._peaks[index.row()][index.column()])
            else:
                assert index.column() == 4
                q, h, k, l, dist0 = self._peaks[index.row()]
                return '{0.val:.4f} \xb1 {0.err:.4f}'.format(2*np.pi/q*(h**2+k**2+l**4)**0.5)
        elif role == QtCore.Qt.EditRole:
            if index.column() in [1,2,3]:
                return self._peaks[index.row()][index.column()]
            else:
                return None
        return None


    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if role==QtCore.Qt.DisplayRole and orientation==QtCore.Qt.Horizontal:
            return ['q (1/nm)','h','k','l','a (nm)','S-D distance (mm)'][section]
        else:
            return None

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = ...):
        if index.column() in [1,2,3] and role == QtCore.Qt.EditRole:
            self._peaks[index.row()][index.column()]=value
            self.dataChanged.emit(self.index(index.row(), index.column()),
                                  self.index(index.row(), index.column()),
                                  [QtCore.Qt.DisplayRole])
            self.calibrationChanged.emit()
            return True
        return False

    def addPeak(self, q:ErrorValue, dist0:ErrorValue, h:int=None, k:int=None, l:int=None):
        if h is None:
            if not self._peaks:
                h=1
            else:
                h=max([p[1] for p in self._peaks])+1
        if k is None:
            k=0
        if l is None:
            l=0
        self.beginInsertRows(QtCore.QModelIndex(), len(self._peaks), len(self._peaks))
        self._peaks.append([q, h, k, l, dist0])
        self.endInsertRows()
        self.calibrationChanged.emit()

    def fitLatticeParameter(self):
        x = np.array([(p[1]**2+p[2]**2+p[3]**2)**0.5 for p in self._peaks])
        y = np.array([p[0].val for p in self._peaks ])
        dy = np.array([p[0].err for p in self._peaks ])
        d, stat = nonlinear_leastsquares(x,y,dy, lambda x, d: 2*np.pi/d*x, [1.0])
        return d, stat