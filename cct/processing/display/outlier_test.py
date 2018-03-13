from typing import Optional

import h5py
import numpy as np
from PyQt5 import QtCore
from matplotlib.figure import Figure


class OutlierModel(QtCore.QAbstractItemModel):
    def __init__(self, parent, group: h5py.Group):
        super().__init__(parent)
        self._data = []
        sortedkeys = sorted(group.keys(), key=lambda x: int(x))
        for fsn in sortedkeys:
            dset = group[fsn]
            self._data.append([
                int(fsn), dset.attrs['date'], dset.attrs['correlmat_discrp'],
                dset.attrs['correlmat_rel_discrp'],
                ['Good', 'BAD'][dset.attrs['correlmat_bad']]])

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 5

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._data)

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.DisplayRole:
            return str(self._data[index.row()][index.column()])
        else:
            return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            return ['FSN', 'Date', 'Discrepancy', 'Relative discrepancy', 'Quality'][section]
        else:
            return None

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def getFSN(self, index: QtCore.QModelIndex):
        return self._data[index.row()][0]


def display_outlier_test_results(grp: h5py.Group) -> OutlierModel:
    return OutlierModel(None, grp)


def display_outlier_test_results_graph(fig: Figure, grp: h5py.Group, factor: float, method: Optional[str] = None):
    fig.clf()
    sortedkeys = sorted(grp.keys(), key=lambda x: int(x))
    fsns = np.array([int(fsn) for fsn in sortedkeys])
    ax = fig.add_subplot(1, 1, 1)
    if method is None:
        discrps = np.array([grp[fsn].attrs['correlmat_discrp'] for fsn in sortedkeys])
        bad = np.array([grp[fsn].attrs['correlmat_bad'] for fsn in sortedkeys])
        lbound = np.nanmedian(discrps) - np.nanstd(discrps) * factor
        ubound = np.nanmedian(discrps) + np.nanstd(discrps) * factor
        ylabel = 'Difference from the others'
    elif method == 'zscore':
        discrps = np.array([grp[fsn].attrs['correlmat_zscore'] for fsn in sortedkeys])
        bad = np.array([grp[fsn].attrs['correlmat_bad_zscore'] for fsn in sortedkeys])
        lbound = -factor
        ubound = factor
        ylabel = 'Z-score'
    elif method == 'zscore_mod':
        discrps = np.array([grp[fsn].attrs['correlmat_zscore_mod'] for fsn in sortedkeys])
        bad = np.array([grp[fsn].attrs['correlmat_bad_zscore_mod'] for fsn in sortedkeys])
        lbound = -factor
        ubound = factor
        ylabel = 'Modified Z-score'
    elif method == 'iqr':
        discrps = np.array([grp[fsn].attrs['correlmat_discrp'] for fsn in sortedkeys])
        bad = np.array([grp[fsn].attrs['correlmat_bad_iqr'] for fsn in sortedkeys])
        p25, p75 = np.percentile(discrps, [25, 75])
        lbound = p25 - factor * (p75 - p25)
        ubound = p75 + factor * (p75 - p25)
        ylabel = 'Difference from the others'

    ax.plot(fsns[~bad], discrps[~bad], 'bo')
    ax.plot(fsns[bad], discrps[bad], 'rs')
    ax.hlines(lbound, fsns.min(), fsns.max(), 'green', '--')
    ax.hlines(ubound, fsns.min(), fsns.max(), 'green', '--')
    ax.fill_between([fsns.min(), fsns.max()], lbound, ubound, color='g', alpha=0.5)
    ax.set_xlabel('File sequence number')
    ax.set_ylabel(ylabel)
    fig.canvas.draw()
    return fig
