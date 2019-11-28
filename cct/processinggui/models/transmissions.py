import typing

import numpy as np
from PyQt5 import QtCore
from sastool.misc.errorvalue import ErrorValue


class TransmissionData:
    samplename: str
    distance: float
    transmission: typing.Union[ErrorValue, float]
    thickness: typing.Union[ErrorValue, float]

    def __init__(self, samplename:str, distance:float, transmission: typing.Union[ErrorValue, float], thickness: typing.Union[ErrorValue, float]):
        self.samplename = samplename
        self.distance = float(distance)
        self.transmission = transmission
        if not isinstance(self.transmission, ErrorValue):
            self.transmission = ErrorValue(self.transmission, 0)
        self.thickness = thickness
        if not isinstance(self.thickness, ErrorValue):
            self.thickness = ErrorValue(self.thickness, 0)

    @property
    def thickness_mm(self):
        return self.thickness * 10

    @property
    def mu_mm(self):
        if self.transmission.val <=0:
            return np.inf
        elif self.transmission.val >=1:
            return 0
        return - self.transmission.log() / self.thickness_mm

    @property
    def abslength_mm(self):
        if self.transmission.val <= 0:
            return 0
        elif self.transmission.val >= 1:
            return np.inf
        return 1/self.mu_mm

class TransmissionModel(QtCore.QAbstractItemModel):
    _columnnames = ['Sample', 'Distance', 'Thickness (mm)', 'Transmission', 'mu (1/mm)', 'Abs.length (mm)']  # fill this
    _data: typing.List[TransmissionData]

    def __init__(self):
        super().__init__()
        self._data = []

    def rowCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._columnnames)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        # edit this to your needs
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return self._data[index.row()].samplename
            elif index.column() == 1:
                return '{:.2f}'.format(self._data[index.row()].distance)
            elif index.column() == 2:
                return '{:.4f}'.format(self._data[index.row()].thickness_mm)
            elif index.column() == 3:
                return '{:.4f}'.format(self._data[index.row()].transmission)
            elif index.column() == 4:
                return '{:.4f}'.format(self._data[index.row()].mu_mm)
            elif index.column() == 5:
                return '{:.4f}'.format(self._data[index.row()].abslength_mm)
        return None

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = None) -> bool:
        # edit this to your needs
        return False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        # edit this to your needs
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._columnnames[section]
        return None

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = None) -> QtCore.QModelIndex:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return self.createIndex(row, column, None)

    def removeRow(self, row: int, parent: QtCore.QModelIndex = None) -> bool:
        return self.removeRows(row, 1, parent)

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = None) -> bool:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        self.beginRemoveRows(QtCore.QModelIndex(), row, row + count)
        for i in reversed(range(row, row + count)):
            del self._data[i]
        self.endRemoveRows()
        return True

    def add(self, samplename: str, distance:float, transmission:ErrorValue, thickness:ErrorValue):
        # edit this to your needs
        self.beginInsertRows(QtCore.QModelIndex(), self.rowCount(), self.rowCount() + 1)
        self._data.append(TransmissionData(samplename, distance, transmission, thickness))
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()