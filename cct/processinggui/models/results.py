import logging
from typing import Optional, Any, List

import h5py
from PyQt5 import QtCore
from sastool.io.credo_cpth5 import Header

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Result:
    samplename: str
    distance: float
    temperature: Optional[float]
    exposurecount: int
    samplecategory: str
    totaltime: float

    def __init__(self, samplename: str, distance: float, temperature: Optional[float], exposurecount: int,
                 samplecategory: str, totaltime: float):
        self.samplename = samplename
        self.distance = distance
        self.temperature = temperature
        self.exposurecount = exposurecount
        self.samplecategory = samplecategory
        self.totaltime = totaltime


class ResultsModel(QtCore.QAbstractItemModel):
    _columnnames = ['Sample', 'Distance', 'Temperature', '#Exposures', 'Total time', 'Category']
    _h5filename: str
    _data: List[Result]
    _lastsortcolumn: int = None
    _lastsortorder: QtCore.Qt.SortOrder = None

    def __init__(self, h5filename: str):
        super().__init__()
        self._h5filename = h5filename
        self._data = None
        self.reload()

    def setH5FileName(self, h5filename: str):
        self._h5filename = h5filename
        self.reload()

    def reload(self):
        logger.debug('Reloading results')
        self.beginResetModel()
        self._data = []
        try:
            with h5py.File(self._h5filename, 'r', swmr=True) as f:
                for samplename in f['Samples']:
                    for dist in f['Samples'][samplename]:
                        # ToDo: temperature
                        g = f['Samples'][samplename][dist]
                        header = Header.new_from_group(g)
                        self._data.append(Result(header.title, header.distance, header.temperature, len(g['curves']),
                                                 header.sample_category, header.exposuretime))
        except OSError:
            self._data = []
        finally:
            self.endResetModel()
        if self._lastsortcolumn is not None and self._lastsortorder is not None:
            self.sort(self._lastsortcolumn, self._lastsortorder)

    def rowCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = None) -> int:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            raise ValueError('This is a flat model')
        return len(self._columnnames)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return self._data[index.row()].samplename
            elif index.column() == 1:
                return '{:.2f}'.format(float(self._data[index.row()].distance))
            elif index.column() == 2:
                return '{:.2f}'.format(float(self._data[index.row()].temperature)) \
                    if self._data[index.row()].temperature is not None else '--'
            elif index.column() == 3:
                return self._data[index.row()].exposurecount
            elif index.column() == 4:
                t = float(self._data[index.row()].totaltime)
                hours = int(t // 3600)
                mins = int((t - hours * 3600) // 60)
                secs = (t - hours * 3600 - mins * 60)
                return '{:02d}:{:02d}:{:.2f}'.format(hours, mins, secs)
            elif index.column() == 5:
                return self._data[index.row()].samplecategory
            else:
                return None
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = None) -> bool:
        # edit this to your needs
        return False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        # edit this to your needs
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> Any:
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

    def sort(self, column: int, order: QtCore.Qt.SortOrder = ...):
        self.beginResetModel()
        attribs = ['samplename', 'distance', 'temperature', 'exposurecount', 'totaltime', 'samplecategory']
        self._data = sorted(self._data, key=lambda x: getattr(x, attribs[column]))
        if order == QtCore.Qt.AscendingOrder:
            self._data = list(reversed(self._data))
        self.endResetModel()
        self._lastsortcolumn = column
        self._lastsortorder = order

    def __getitem__(self, item: int) -> Result:
        return self._data[item]
