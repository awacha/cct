import datetime
import logging
import typing

import numpy as np
import sastool
from PyQt5 import QtCore
from sastool.classes2 import Header

from ..config import Config

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class HeaderList(QtCore.QAbstractItemModel):
    """A simple flat (non-hierarchical) model for storing metadata of exposures

    The first column is always the file sequence number. Further columns can be
    selected.
    """
    allColumns = {'fsn'             : 'FSN', 'title': 'Sample', 'energy': 'Energy', 'wavelength': 'Wavelength',
                   'distance'        : 'S-D dist.', 'temperature': 'Temperature', 'beamcenterx': 'Beam X',
                   'beamcentery'     : 'Beam Y', 'pixelsizex': 'Pixel size X', 'pixelsizey': 'Pixel size Y',
                   'exposuretime'    : 'Exposure time',
                   'startdate'       : 'Start date', 'enddate': 'End date', 'date': 'Date', 'maskname': 'Mask name',
                   'vacuum'          : 'Vacuum',
                   'transmission'    : 'Transmission', 'flux': 'Flux', 'thickness': 'Thickness',
                   'distancedecrease': 'Dist.decr.',
                   'samplex'         : 'Sample X', 'sampley': 'Sample Y', 'username': 'User name', 'project': 'Project',
                   'fsn_emptybeam'   : 'FSN empty',
                   'fsn_absintref'   : 'FSN absintref', 'absintfactor': 'Abs.int.factor'}

    _data: typing.List[Header]
    _columnnames: typing.List[str] = ['fsn', 'title', 'distance', 'startdate', 'flux', 'vacuum']  # fill this
    _badfsns: typing.List[int]
    _config: Config

    def __init__(self, config: Config):
        super().__init__()
        self._data = []
        self._badfsns:List[int] = []
        self._config = config
        try:
            # noinspection PyTypeChecker
            self._badfsns = np.loadtxt(self._config.badfsnsfile, dtype=np.int).flatten().tolist()
        except OSError:
            self._badfsns = []
        self.updateColumnChoices(self._config.fields)
        self._config.configItemChanged.connect(self.onConfigItemChanged)

    def onConfigItemChanged(self, sectionname:str, itemname:str, newvalue:typing.Any):
        logger.debug('ConfigItemChanged signal caught in header list. Item name: {}. Value: {}'.format(itemname, newvalue))
        if itemname == 'fields':
            self.updateColumnChoices(newvalue)

    def updateColumnChoices(self, columns: typing.List[str]):
        """Update the displayed columns in this model.
        """
        invalidcolumns = [c for c in columns if c not in self.allColumns]
        if invalidcolumns:
            raise ValueError('Unknown column(s): {}'.format(', '.join(invalidcolumns)))
        self.beginResetModel()
        self._columnnames = ['fsn'] + columns  # the first column is always 'fsn'
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._columnnames)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            return [QtCore.Qt.Unchecked, QtCore.Qt.Checked][self._data[index.row()].fsn in self._badfsns]
        elif role == QtCore.Qt.DisplayRole:
            value = getattr(self._data[index.row()], self._columnnames[index.column()])
            if isinstance(value, int):
                return str(value)
            elif isinstance(value, datetime.datetime):
                return str(value)
            elif isinstance(value, sastool.ErrorValue):
                return value.tostring(plusminus=' \xb1 ')
            elif isinstance(value, float):
                return '{:.4f}'.format(value)
            elif value is None:
                return '--'
            elif isinstance(value, str):
                return value
            else:
                raise TypeError('Invalid type for column {}: {}'.format(self._columnnames[index.column()], type(value)))
        # edit this to your needs
        return None

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = None) -> bool:
        if index.column() == 0 and role == QtCore.Qt.CheckStateRole:
            self._badfsns = [f for f in self._badfsns if f != self._data[index.row()].fsn]
            if bool(value):
                self._badfsns.append(self._data[index.row()].fsn)
            self.writeBadFSNs()
            return True
        return False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        # edit this to your needs
        if index.column() > 0:
            if self._data[index.row()].fsn in self._badfsns:
                return QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren
            else:
                return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsUserCheckable

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> typing.Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self.allColumns[self._columnnames[section]]
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

    def add(self, item: Header):
        # edit this to your needs
        if not isinstance(item, Header):
            raise TypeError('Only an instance of Header can be added to this model.')
        self.beginInsertRows(QtCore.QModelIndex(), self.rowCount(), self.rowCount() + 1)
        self._data.append(item)
        self.endInsertRows()

    def writeBadFSNs(self):
        # noinspection PyTypeChecker
        np.savetxt(self._config.badfsnsfile, self._badfsns, fmt='%.0f')

    def replaceAllHeaders(self, headers:typing.List[Header]):
        self.beginResetModel()
        self._data = headers
        self.endResetModel()

    def __getitem__(self, row:int):
        return self._data[row]
