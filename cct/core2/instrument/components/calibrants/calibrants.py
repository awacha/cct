import datetime
import re
from typing import List, Any
import logging

import dateutil.parser
from PyQt5 import QtCore

from .calibrant import Calibrant
from .intensity import IntensityCalibrant
from .q import QCalibrant
from ..component import Component

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class CalibrantStore(QtCore.QAbstractItemModel, Component):
    _calibrants: List[Calibrant]
    calibrantListChanged = QtCore.pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._calibrants = []
        self.loadFromConfig()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        if not parent.isValid():
            return 2  # Q calibrants, intensity calibrants
        elif isinstance(parent.internalPointer(), Calibrant):
            return 0
        elif parent.row() == 0:
            return len(self.qcalibrants())
        elif parent.row() == 1:
            return len(self.intensitycalibrants())
        else:
            assert False

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 4  # name, regex, date, data

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Name', 'Regular expression', 'Date', 'Data'][section]

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        if not parent.isValid():
            assert row in [0, 1]
            return self.createIndex(row, column, None)
        elif parent.internalPointer() is None:
            return self.createIndex(row, column,
                                    self.qcalibrants()[row] if parent.row() == 0 else self.intensitycalibrants()[row])
        else:
            assert False

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not child.isValid():
            return QtCore.QModelIndex()
        elif child.internalPointer() is None:
            return QtCore.QModelIndex()
        elif isinstance(child.internalPointer(), QCalibrant):
            return self.index(0, 0, QtCore.QModelIndex())
        elif isinstance(child.internalPointer(), IntensityCalibrant):
            return self.index(1, 0, QtCore.QModelIndex())
        else:
            assert False

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if not index.isValid():
            return None
        elif index.internalPointer() is None:
            if index.column() == 0 and role == QtCore.Qt.DisplayRole:
                return ['Q calibrants', 'Intensity calibrants'][index.row()]
        else:
            calibrant = index.internalPointer()
            assert isinstance(calibrant, Calibrant)
            if (index.column() == 0) and (role in [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]):
                return calibrant.name
            elif (index.column() == 1) and (role in [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]):
                return calibrant.regex
            elif (index.column() == 2) and (role in [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]):
                return str(calibrant.calibrationdate) if role == QtCore.Qt.DisplayRole else calibrant.calibrationdate
            elif (index.column() == 3) and (role == QtCore.Qt.DisplayRole):
                if isinstance(calibrant, QCalibrant):
                    return f'{len(calibrant)} peaks'
                elif isinstance(calibrant, IntensityCalibrant):
                    return calibrant.datafile
            elif (index.column() == 0) and (role == QtCore.Qt.ToolTipRole):
                return calibrant.description

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if (not index.isValid()) or (index.internalPointer() is None):
            return False
        if role != QtCore.Qt.EditRole:
            return False
        calibrant = index.internalPointer()
        assert isinstance(calibrant, Calibrant)
        if index.column() == 0:
            if value in [c.name for c in self._calibrants]:
                return False
            calibrant.name = value
        elif index.column() == 1:
            try:
                re.compile(value)
            except re.error:
                return False
            calibrant.regex = value
        elif index.column() == 2:
            if isinstance(value, str):
                try:
                    calibrant.calibrationdate = dateutil.parser.parse(value)
                except dateutil.parser.ParserError:
                    return False
            elif isinstance(value, QtCore.QDateTime):
                calibrant.calibrationdate = datetime.datetime(value.date().year(), value.date().month(), value.date().day(), value.time().hour(), value.time().minute(), value.time().second())
            elif isinstance(value, datetime.datetime):
                calibrant.calibrationdate = value
            else:
                return False
        self.dataChanged.emit(index, index)
        self.saveToConfig()
        self.calibrantListChanged.emit()
        return True

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if index.isValid() and isinstance(index.internalPointer(), Calibrant) and index.column() in [0, 1, 2]:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        elif index.isValid() and isinstance(index.internalPointer(), Calibrant):
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        else:
            return QtCore.Qt.ItemIsEnabled

    def qcalibrants(self) -> List[QCalibrant]:
        return [c for c in self._calibrants if isinstance(c, QCalibrant)]

    def intensitycalibrants(self) -> List[IntensityCalibrant]:
        return [c for c in self._calibrants if isinstance(c, IntensityCalibrant)]

    def loadFromConfig(self):
        self.beginResetModel()
        self._calibrants = []
        if 'calibrants' in self.config:
            for calibrantname in self.config['calibrants']:
                conf = self.config['calibrants'][calibrantname].asdict()
                if all([(isinstance(v, dict) and ('val' in v) and ('err' in v)) for k, v in conf.items()]):
                    # this is an old-style q-calibrant
                    calibrant = QCalibrant(calibrantname)
                    calibrant.__setstate__({'name': calibrantname,
                                            'description': '',
                                            'regex': '^' + calibrantname + '$',
                                            'calibrationdate': str(datetime.datetime.now()),
                                            'peaks': [
                                                (peakname, conf[peakname]['val'], conf[peakname]['err'])
                                                for peakname in sorted(conf)
                                            ]
                                            })
                elif 'peaks' in conf:
                    calibrant = QCalibrant(calibrantname)
                    calibrant.__setstate__(conf)
                elif 'datafile' in conf:
                    calibrant = IntensityCalibrant(calibrantname)
                    calibrant.__setstate__(conf)
                else:
                    assert False
                self._calibrants.append(calibrant)
        self._calibrants.sort(key=lambda c: c.name)
        self.endResetModel()
        self.calibrantListChanged.emit()

    def saveToConfig(self):
        for c in self._calibrants:
            self.config['calibrants'][c.name] = c.__getstate__()
        missing = [k for k in self.config['calibrants'] if k not in [c.name for c in self._calibrants]]
        for k in missing:
            del self.config['calibrants'][k]

    def addQCalibrant(self):
        i = 0
        while f'Untitled{i}' in [c.name for c in self._calibrants]:
            i += 1
        self.beginResetModel()
        self._calibrants.append(QCalibrant(f'Untitled{i}'))
        self._calibrants.sort(key=lambda c: c.name)
        self.endResetModel()
        self.saveToConfig()
        self.calibrantListChanged.emit()

    def addIntensityCalibrant(self):
        i = 0
        while f'Untitled{i}' in [c.name for c in self._calibrants]:
            i += 1
        self.beginResetModel()
        self._calibrants.append(IntensityCalibrant(f'Untitled{i}'))
        self._calibrants.sort(key=lambda c: c.name)
        self.endResetModel()
        self.saveToConfig()
        self.calibrantListChanged.emit()

    def removeCalibrant(self, name: str):
        calibrant = [c for c in self._calibrants if c.name == name][0]
        if isinstance(calibrant, QCalibrant):
            self.beginRemoveRows(self.index(0, 0, QtCore.QModelIndex()), self.qcalibrants().index(calibrant), self.qcalibrants().index(calibrant))
        elif isinstance(calibrant, IntensityCalibrant):
            self.beginRemoveRows(self.index(1, 0, QtCore.QModelIndex()), self.intensitycalibrants().index(calibrant), self.intensitycalibrants().index(calibrant))
        else:
            assert False
        self._calibrants.remove(calibrant)
        self.endRemoveRows()
        self.saveToConfig()
        self.calibrantListChanged.emit()
