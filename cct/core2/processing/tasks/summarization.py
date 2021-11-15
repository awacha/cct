import logging
import multiprocessing
import queue
from typing import List, Any, Optional, Sequence, Iterator, Set

from PyQt5 import QtCore, QtGui

from .task import ProcessingTask, ProcessingStatus, ProcessingSettings
from ..calculations.backgroundprocess import Message
from ..calculations.summaryjob import SummaryJob, SummaryJobResults, Results

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SummaryData:
    samplename: str
    distance: float
    fsns: List[int]
    statusmessage: str = '--'
    spinner: Optional[int] = None
    progresstotal: int = 0
    progresscurrent: int = 0
    errormessage: Optional[str] = None
    traceback: Optional[str] = None
    lastfoundbadfsns: List[int]

    def __init__(self, samplename: str, distance: float, fsns: Sequence[int], ):
        self.samplename = samplename
        self.distance = distance
        self.fsns = list(fsns)
        self.lastfoundbadfsns = []

    def isRunning(self) -> bool:
        return self.spinner is not None


class Summarization(ProcessingTask):
    _data: List[SummaryData] = None
    itemChanged = QtCore.pyqtSignal(str, str)
    newbadfsns: Set[int]
    spinnerTimer: Optional[QtCore.QTimer] = None

    def __init__(self, processing: "Processing", settings: ProcessingSettings):
        self._data = []
        self.newbadfsns = set()
        super().__init__(processing, settings)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 5

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        sd = self._data[index.row()]
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return sd.samplename
            elif index.column() == 1:
                return f'{sd.distance:.2f} mm'
            elif index.column() == 2:
                return str(len([f for f in sd.fsns if f not in self.settings.badfsns]))
            elif index.column() == 3:
                return str(len(sd.fsns))
            elif index.column() == 4:
                return sd.statusmessage if sd.errormessage is None else sd.errormessage
        elif (role == QtCore.Qt.DecorationRole) and (sd.spinner is not None) and (index.column() == 0):
            return QtGui.QIcon(QtGui.QPixmap(f':/icons/spinner_{sd.spinner % 12:02d}.svg'))
        elif (role == QtCore.Qt.ToolTipRole) and (sd.errormessage is not None):
            return sd.traceback
        elif (role == QtCore.Qt.BackgroundColorRole) and (sd.errormessage is not None):
            return QtGui.QColor('red').lighter(0.5)
        elif (role == QtCore.Qt.TextColorRole) and (sd.errormessage is not None):
            return QtGui.QColor('black')

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Sample', 'Distance', 'Good', 'All', 'Status'][section]

    def __iter__(self) -> Iterator[SummaryData]:
        yield from self._data

    def addSample(self, samplename: str, distance: float, fsns: Sequence[int]):
        logger.debug('Checking if this sample exists.')
        if [sd for sd in self._data if sd.samplename == samplename and sd.distance == distance]:
            raise ValueError('Already existing (samplename, distance) pair.')
        logger.debug('Invoking beginResetModel')
        self.beginResetModel()
        logger.debug(f'Adding sample {samplename=}, {distance=}')
        self._data.append(SummaryData(samplename, distance, fsns))
        logger.debug(f'Created SummaryData instance.')
        self._data = sorted(self._data, key=lambda sd: (sd.samplename, sd.distance))
        logger.debug('Sorted model')
        self.endResetModel()
        logger.debug('Emitted endResetModel')

    def clear(self):
        if not self.isIdle():
            raise RuntimeError('Cannot clear summarization model: not idle.')
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def _start(self):
        self.newbadfsns = set()
        for i, sd in enumerate(self._data):
            sd.errormessage = None
            sd.traceback = None
            sd.spinner = 0
            logger.debug(f'{self.settings.badfsns=}')
            self._submitTask(SummaryJob.run, (i, sd.samplename, sd.distance),
                             rootpath=self.settings.rootpath,
                             eval2dsubpath=self.settings.eval2dsubpath,
                             masksubpath=self.settings.masksubpath,
                             fsndigits=self.settings.fsndigits,
                             prefix=self.settings.prefix,
                             fsnlist=list(sd.fsns),
                             ierrorprop=self.settings.ierrorprop,
                             qerrorprop=self.settings.qerrorprop,
                             outliermethod=self.settings.outliermethod,
                             outlierthreshold=self.settings.outlierthreshold,
                             cormatLogarithmic=self.settings.outlierlogcormat,
                             qrange=None,  # ToDo
                             bigmemorymode=self.settings.bigmemorymode,
                             badfsns=self.settings.badfsns
                             )
            sd.statusmessage = 'Queued for processing...'
        self.dataChanged.emit(self.index(0, 0, QtCore.QModelIndex()),
                              self.index(self.rowCount(), self.columnCount(), QtCore.QModelIndex()))
        self.spinnerTimer = QtCore.QTimer()
        self.spinnerTimer.timeout.connect(self.updateSpinners)
        self.spinnerTimer.setTimerType(QtCore.Qt.PreciseTimer)
        self.spinnerTimer.start(100)

    def onBackgroundTaskProgress(self, jobid: Any, total: int, current: int, message: str):
        j = jobid[0]
        self._data[j].progresstotal = total
        self._data[j].progresscurrent = current
        self._data[j].statusmessage = message
        self.dataChanged.emit(self.index(j, 4), self.index(j, 4))

    def onBackgroundTaskError(self, jobid: Any, errormessage: str, traceback: str):
        j = jobid[0]
        self._data[j].errormessage = errormessage
        self._data[j].traceback = traceback
        self._data[j].spinner = None
        self.dataChanged.emit(self.index(j, 0), self.index(j, self.columnCount()))
        super().onBackgroundTaskError(jobid, errormessage, traceback)

    def onBackgroundTaskFinished(self, result: Any):
        logger.debug(f'Summarization result: {result}')
        i, samplename, distance = result.jobid
        self._data[i].progresscurrent = 0
        self._data[i].progresstotal = 0
        self._data[i].spinner = None
        self._data[i].lastfoundbadfsns = result.newbadfsns
        self.newbadfsns = self.newbadfsns.union(result.newbadfsns)
        self._data[i].statusmessage = 'Processing done'
        #self.itemChanged.emit(self._data[i].samplename, f'{self._data[i].distance:.2f}')
        self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount()))
        self.itemChanged.emit(self._data[i].samplename, f'{self._data[i].distance:.2f}')
        super().onBackgroundTaskFinished(result)

    def onAllBackgroundTasksFinished(self):
        self.settings.addBadFSNs(self.newbadfsns)
        for i,d in enumerate(self._data):
            if d.spinner is not None:
                d.errormessage = 'User break'
                d.spinner = None
                self.dataChanged.emit(self.index(i, 0, QtCore.QModelIndex()), self.index(i, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def updateSpinners(self):
        # update spinners
        for d in self._data:
            if d.spinner is not None:
                d.spinner += 1
        self.dataChanged.emit(
            self.index(0, 0, QtCore.QModelIndex()),
            self.index(self.rowCount(QtCore.QModelIndex()), 0, QtCore.QModelIndex()), [QtCore.Qt.DecorationRole])
        if not [d for d in self._data if d.spinner is not None]:
            self.spinnerTimer.stop()
            self.spinnerTimer.deleteLater()
            self.spinnerTimer = None
