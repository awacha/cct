import datetime
import logging
import os
from typing import Dict, Optional, Any, Sequence

from PyQt5 import QtCore

from .component import Component
from ...dataclasses import Scan

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ScanStore(QtCore.QAbstractItemModel, Component):
    """Scan subsystem of the instrument, responsible for reading and writing scan files.
    """
    _scans: Dict[int, Scan]
    _lastscan: Optional[int] = None
    _nextscan: int = 0
    nextscanchanged = QtCore.pyqtSignal(int)
    lastscanchanged = QtCore.pyqtSignal(int)
    _scanning: Optional[int] = None
    scanstarted = QtCore.pyqtSignal(int, int)
    scanpointreceived = QtCore.pyqtSignal(int, int, int, tuple)
    scanfinished = QtCore.pyqtSignal(int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._scans = {}
        self._lastscan = None
        self._nextscan = 0
        self._scanning = None
        self.reindex()

    def newScanFile(self, filename: str):
        pass

    def startNewScan(self, command: str, motorname: str, counters: Sequence[str], maxcounts: int, comment: str,
                     countingtime: float) -> int:
        assert self._nextscan not in self._scans
        self.beginInsertRows(QtCore.QModelIndex(), len(self._scans), len(self._scans))
        self._scans[self._nextscan] = Scan(motorname, counters, maxcounts, self._nextscan, datetime.datetime.now(),
                                           comment, command, countingtime)
        self.endInsertRows()
        with open(self.scanfile(), 'at') as f:
            f.write(f'\n#S {self._nextscan}  {command}\n')
            f.write(f'#D {str(datetime.datetime.now())}\n')
            f.write(f'#C {comment}\n')
            f.write(f'#T {countingtime:.6f}  (Seconds)\n')
            f.write(f'#G0 0\n')
            f.write(f'#G1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n')
            f.write(f'#Q 0 0 0\n')
            motorpos = [m.where() for m in self.instrument.motors]
            for i in range(len(motorpos) // 8 + 1):
                if motorpos[i * 8:i * 8 + 8]:  # avoid an empty line
                    f.write(f'#P{i} ' + ' '.join([str(mp) for mp in motorpos[i * 8:i * 8 + 8]]) + '\n')

            f.write(f'#N {maxcounts}\n')
            f.write(f'#L ' + '  '.join([motorname] + list(counters)) + '\n')
            # header ready.
        self._scanning = self._nextscan
        self._nextscan += 1
        self.nextscanchanged.emit(self._nextscan)
        self.scanstarted.emit(self._scanning, maxcounts)

    def addScanLine(self, readings: Sequence[float]):
        if self._scanning is None:
            raise RuntimeError('No scan running')
        scan = self._scans[self._scanning]
        if len(readings) != len(scan.columnnames):
            raise ValueError('Reading count mismatch.')
        scan.append(tuple(readings))
        with open(self.scanfile(), 'at') as f:
            f.write(' '.join([str(x) for x in readings]) + '\n')
        self.scanpointreceived.emit(self._scanning, len(scan) - 1, scan.maxpoints(), tuple(readings))
        self.dataChanged.emit(self.index(list(self._scans.keys()).index(scan.index), 5),
                              self.index(list(self._scans.keys()).index(scan.index), 5))
        if scan.finished():
            self.finishScan()

    def finishScan(self):
        if self._scanning is None:
            raise ValueError('No running scan')
        with open(self.scanfile(), 'at') as f:
            f.write('\n')
        self.scanfinished.emit(self._scanning)
        self._scanning = None

    def scanfile(self) -> str:
        return os.path.join(self.config['path']['directories']['scan'],
                            self.config['scan']['scanfile'])

    def onConfigChanged(self, path, value):
        if path == ('scan', 'scanfile'):
            self.reindex()

    def reindex(self):
        self.beginResetModel()
        try:
            self._scans = {}
            with open(os.path.join(self.config['path']['directories']['scan'],
                                   self.config['scan']['scanfile']), 'rb') as f:
                while True:
                    try:
                        scan = Scan.fromspecfile(f, None)
                        self._scans[scan.index] = scan
                    except ValueError:
                        break
            self._lastscan = max(self._scans.keys()) if self._scans else None
            self._nextscan = self._lastscan + 1 if self._lastscan is not None else 0
        finally:
            self.endResetModel()
        self.lastscanchanged.emit(self._lastscan)
        self.nextscanchanged.emit(self._nextscan)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 7

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._scans)

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        scan = self._scans[list(self._scans.keys())[index.row()]]
        if role == QtCore.Qt.UserRole:
            return scan
        elif role == QtCore.Qt.ToolTipRole:
            return scan.command
        elif role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return str(scan.index)
            elif index.column() == 1:
                return str(scan.date)
            elif index.column() == 2:
                return scan.motorname
            elif index.column() == 3:
                return str(scan[scan.motorname][0])
            elif index.column() == 4:
                return str(scan[scan.motorname][-1])
            elif index.column() == 5:
                return len(scan)
            elif index.column() == 6:
                return scan.comment

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Index', 'Date', 'Motor', 'From', 'To', 'Length', 'Comment'][section]

    def lastscan(self) -> int:
        return self._lastscan

    def nextscan(self) -> int:
        return self._nextscan

    def firstscan(self) -> int:
        return min(self._scans)

    def __getitem__(self, item) -> Scan:
        return self._scans[item]
