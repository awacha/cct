# coding: utf-8
"""List model for slice information"""
import itertools
from typing import List, Any, Iterator, Optional

import matplotlib
from PyQt5 import QtCore, QtGui


class SectorInformation:
    phi0: float = 0.0
    dphi: float = 10
    symmetric: bool = True
    color: QtGui.QColor = QtGui.QColor('black')


class SectorModel(QtCore.QAbstractItemModel):
    """List model for sectors in the azimuthal angle"""

    _data: List[SectorInformation]
    color_iterator: Iterator[str]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._reset_colors_iterator()

    def _reset_colors_iterator(self):
        colors = []
        for styleentry in matplotlib.rcParams['axes.prop_cycle']:
            if 'color' in styleentry:
                colors.append(styleentry['color'])
        if not colors:
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22',
                      '#17becf']
        self.color_iterator = itertools.cycle(self.color_iterator)

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 4

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if index.column() == 0:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        elif index.column() == 1:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        elif index.column() == 2:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        elif index.column() == 3:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable, QtCore.Qt.ItemIsUserCheckable

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        si = self._data[index.row()]
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return si.color.name()
            elif index.column() == 1:
                return f'{si.phi0:.2f}'
            elif index.column() == 2:
                return f'{si.dphi:.2f}'
            elif index.column() == 3:
                return 'Symmetric' if si.symmetric else 'Asymmetric'
        elif role == QtCore.Qt.DecorationRole:
            if index.column() == 0:
                return si.color
        elif role == QtCore.Qt.CheckStateRole:
            if index.column() == 3:
                return QtCore.Qt.Checked if si.symmetric else QtCore.Qt.Unchecked
        elif role == QtCore.Qt.EditRole:
            if index.column() == 0:
                return si.color
            elif index.column() == 1:
                return si.phi0, 0, 360.0
            elif index.column() == 2:
                return si.dphi, 0, 360.0
            elif index.column() == 3:
                return si.symmetric
        elif role == QtCore.Qt.UserRole:
            return si

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        si = self._data[index.row()]
        if (index.column() == 0) and (role == QtCore.Qt.EditRole):
            if isinstance(value, QtGui.QColor):
                si.color = value
            elif isinstance(value, str):
                si.color = QtGui.QColor(value)
            else:
                return False
        elif (index.column() == 1) and (role == QtCore.Qt.EditRole):
            si.phi0 = float(value)
        elif (index.column() == 2) and (role == QtCore.Qt.EditRole):
            si.dphi = float(value)
        elif (index.column() == 3) and (role == QtCore.Qt.CheckStateRole):
            si.symmetric = value == QtCore.Qt.Checked
        self.dataChanged.emit(
            self.index(index.row(), index.column(), QtCore.QModelIndex()),
            self.index(index.row(), index.column(), QtCore.QModelIndex()))
        return True

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Colour', 'Center (°)', 'Width (°)', 'Symmetric'][section]

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.insertRows(row, 1, parent)

    def insertRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginInsertRows(parent, row, row + count - 1)
        for i in range(count):
            si = SectorInformation()
            si.color = QtGui.QColor(next(self.color_iterator))
            self._data.insert(row, si)
        self.endInsertRows()

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.removeRows(row, 1, parent)

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginRemoveRows(parent, row, row+count-1)
        del self._data[row:row+count]
        self.endRemoveRows()

    def appendSector(self, phi0: float, dphi: float, symmetric: bool, color: Optional[str]):
        si = SectorInformation()
        si.phi0 = phi0
        si.dphi = dphi
        si.symmetric = symmetric
        si.color = QtGui.QColor(color if color is not None else next(self.color_iterator))
        self.beginInsertRows(
            QtCore.QModelIndex(), self.rowCount(QtCore.QModelIndex()), self.rowCount(QtCore.QModelIndex()))
        self._data.append(si)
        self.endInsertRows()

    def __iter__(self) -> Iterator[SectorInformation]:
        return iter(self._data)

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()