import datetime
import logging
import multiprocessing.pool
import os
import time
from typing import Dict, Optional, Any, Sequence

from PyQt5 import QtCore

from .recorder import ScanRecorder
from ..component import Component
from ..motors import Motor
from ....dataclasses import Scan

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ScanStore(QtCore.QAbstractItemModel, Component):
    """Scan subsystem of the instrument, responsible for reading and writing scan files.
    """
    _scans: Dict[int, Scan]
    _lastscan: Optional[int] = None
    _nextscan: int = 0
    nextscanchanged = QtCore.pyqtSignal(int)
    lastscanchanged = QtCore.pyqtSignal(int)
    scanstarted = QtCore.pyqtSignal(int, int)  # scanindex, number of steps
    scanpointreceived = QtCore.pyqtSignal(int, int, int, tuple)  # scanindex, current scan point, total number of scan points, readings
    scanprogress = QtCore.pyqtSignal(float, float, float, str)  # start, end, current, message
    scanfinished = QtCore.pyqtSignal(bool, int)
    scanrecorder: Optional[ScanRecorder] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._scans = {}
        self._lastscan = None
        self._nextscan = 0

    def startComponent(self):
        self.reindex()
        super().startComponent()

    def newScanFile(self, filename: str):
        with open(filename, 'wt') as f:
            f.write(f'#F {os.path.abspath(filename)}\n')
            f.write(f'#E {time.time()}\n')
            f.write(f'#D {datetime.datetime.now()}\n')
            f.write('#C CREDO scan file')
            f.write('#O0 ' + '  '.join([m.name for m in self.instrument.motors]) + '\n')
            f.write('\n\n')

    def startScan(self, motorname: str, rangemin: float, rangemax: float, steps: int, relative: bool,
                  countingtime: float, comment: str, movemotorback: bool = True, shutter: bool = True):
        if self._panicking != self.PanicState.NoPanic:
            raise RuntimeError('Cannot start scan: panic!')
        if self.scanrecorder is not None:
            raise RuntimeError('Cannot start scan: already running')
        try:
            motor = self.instrument.motors[motorname]
        except KeyError:
            raise RuntimeError(f'Invalid motor {motorname}')
        assert isinstance(motor, Motor)

        scan = self.writeNewScanEntry(
            f'{"scanrel" if relative else "scan"}("{motorname}", {rangemin:g}, {rangemax:g}, {steps:d}, '
            f'{countingtime:g}, "{comment}")',
            motorname, steps, countingtime, comment)
        where = motor.where()
        self.scanrecorder = ScanRecorder(
            scan.index, (rangemin + where) if relative else rangemin, (rangemax + where) if relative else rangemax,
            steps, countingtime, motor, self.instrument, movemotorback, shutter
        )
        self.scanrecorder.finished.connect(self.onScanFinished)
        self.scanrecorder.scanpoint.connect(self.addScanLine)
        self.scanrecorder.progress.connect(self.onScanProgress)
        self.scanrecorder.start()
        self.scanstarted.emit(self.scanrecorder.scanindex, steps)

    def onScanProgress(self, start:float, end:float, current:float, message:str):
        self.scanprogress.emit(start, end, current, message)

    def stopScan(self):
        if self.scanrecorder is None:
            raise RuntimeError('No scan to stop')
        self.scanrecorder.stop()

    def writeNewScanEntry(self, command: str, motorname: str, maxcounts: int,
                          countingtime: float, comment: str) -> Scan:
        assert self._nextscan not in self._scans
        counters = ['FSN', 'total_sum', 'sum', 'total_max', 'max', 'total_beamx', 'beamx', 'total_beamy', 'beamy',
                    'total_sigmax', 'sigmax', 'total_sigmay', 'sigmay', 'total_sigma', 'sigma']
        self.beginInsertRows(QtCore.QModelIndex(), len(self._scans), len(self._scans))
        scanindex = self._nextscan
        self._scans[scanindex] = Scan(motorname, counters, maxcounts, scanindex, datetime.datetime.now(),
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
            f.write(f'#L ' + '  '.join([motorname] + counters) + '\n')
            # header ready.
        scanindex = self._nextscan
        self._nextscan += 1
        self.nextscanchanged.emit(self._nextscan)
        self._lastscan = scanindex
        self.lastscanchanged.emit(self._lastscan)
        return self._scans[scanindex]

    def addScanLine(self, readings: Sequence[float]):
        if self.scanrecorder is None:
            raise RuntimeError('No scan running')
        scan = self._scans[self.scanrecorder.scanindex]
        if len(readings) != len(scan.columnnames):
            raise ValueError(f'Reading count mismatch. {len(readings)=}, {len(scan.columnnames)=}, {scan.columnnames=}')
        scan.append(tuple(readings))
        with open(self.scanfile(), 'at') as f:
            f.write(' '.join([str(x) for x in readings]) + '\n')
        self.scanpointreceived.emit(self.scanrecorder.scanindex, len(scan) - 1, scan.maxpoints(), tuple(readings))
        self.dataChanged.emit(self.index(list(self._scans.keys()).index(scan.index), 5),
                              self.index(list(self._scans.keys()).index(scan.index), 5))

    def onScanFinished(self, success: bool, message: str):
        with open(self.scanfile(), 'at') as f:
            f.write('\n')
#        self.lastscanchanged.emit(self.scanrecorder.scanindex)
        self.scanfinished.emit(success, self.scanrecorder.scanindex)
        self.scanrecorder.deleteLater()
        self.scanrecorder = None
        if self._panicking == self.PanicState.Panicking:
            super().panichandler()

    def scanfile(self) -> str:
        return os.path.join(self.config['path']['directories']['scan'],
                            self.config['scan']['scanfile'])

    def onConfigChanged(self, path, value):
        if path == ('scan', 'scanfile'):
            self.reindex()

    def reindex(self):
        self.beginResetModel()
        os.makedirs(self.config['path']['directories']['scan'], exist_ok=True)
        self._scans = {}
        try:
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
        except FileNotFoundError:
            # we need to create a new scan file
            self.newScanFile(os.path.join(self.config['path']['directories']['scan'],
                                          self.config['scan']['scanfile']))
        finally:
            self.endResetModel()
        self.lastscanchanged.emit(self._lastscan if self._lastscan is not None else -1)
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
                try:
                    return str(scan[scan.motorname][0])
                except IndexError:
                    return '--'
            elif index.column() == 4:
                try:
                    return str(scan[scan.motorname][-1])
                except IndexError:
                    return '--'
            elif index.column() == 5:
                return len(scan)
            elif index.column() == 6:
                return scan.comment

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Index', 'Date', 'Motor', 'From', 'To', 'Length', 'Comment'][section]

    def lastscan(self) -> Optional[int]:
        return self._lastscan

    def nextscan(self) -> int:
        return self._nextscan

    def firstscan(self) -> Optional[int]:
        return min(self._scans) if self._scans else None

    def __getitem__(self, item) -> Scan:
        return self._scans[item]

    def loadFromConfig(self):
        if 'scan' not in self.config:
            self.config['scan'] = {'mask': None, 'mask_total': None, 'scanfile': 'credoscan.spec'}

    def panichandler(self):
        self._panicking = self.PanicState.Panicking
        if self.scanrecorder is None:
            super().panichandler()
        else:
            self.stopScan()