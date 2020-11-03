import enum
import multiprocessing
import queue
from typing import List, Any, Optional, Sequence

from PyQt5 import QtCore

from .task import ProcessingTask, ProcessingStatus, ProcessingSettings
from ..calculations.backgroundprocess import Message
from ..calculations.summaryjob import SummaryJob, SummaryJobResults


class SummarizationStatus(enum.Enum):
    Idle = 'idle'
    Stopping = 'user stop requested'
    Running = 'running'


class SummaryData:
    samplename: str
    distance: float
    fsns: List[int]
    statusmessage: str = '--'
    spinner: Optional[int] = None
    progresstotal: int = 0
    progresscurrent: int = 0
    errormessage: Optional[str]
    traceback: Optional[str]

    def __init__(self, samplename: str, distance: float, fsns: Sequence[int], ):
        self.samplename = samplename
        self.distance = distance
        self.fsns = list(fsns)

    def isRunning(self) -> bool:
        return self.spinner is not None


class Summarization(ProcessingTask):
    _data: List[SummaryData] = None

    def __init__(self, settings: ProcessingSettings):
        self._data = []
        super().__init__(settings)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 4

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
                return f'{sd.distance[0]:.2f} mm'
            elif index.column() == 2:
                return

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Sample', 'Distance', 'Good', 'All', 'Status'][section]

    def addSample(self, samplename: str, distance: float, fsns: Sequence[int]):
        if [sd for sd in self._data if sd.samplename == samplename and sd.distance == distance]:
            raise ValueError('Already existing (samplename, distance) pair.')
        self.beginResetModel()
        self._data.append(SummaryData(samplename, distance, fsns))
        self._data = sorted(self._data, key=lambda sd: (sd.samplename, sd.distance))
        self.endResetModel()

    def clear(self):
        if not self.isIdle():
            raise RuntimeError('Cannot clear summarization model: not idle.')
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def start(self):
        if not self.isIdle():
            raise ValueError('Already running')
        self.status = SummarizationStatus.Running
        self._pool = multiprocessing.Pool()
        self._messageQueue = multiprocessing.Queue()
        self._stopEvent = multiprocessing.Event()
        self._asyncresults = []
        for i, sd in enumerate(self._data):
            self._asyncresults.append(
                self._pool.apply_async(
                    SummaryJob.run,
                    kwds={'h5file': self.settings.h5filename,
                          'h5lock': self.settings.h5lock,
                          'jobid': (i, sd.samplename, sd.distance),
                          'stopEvent': self._stopEvent,
                          'messagequeue': self._messageQueue,
                          'rootpath': self.settings.rootpath,
                          'eval2dsubpath': self.settings.eval2dsubpath,
                          'masksubpath': self.settings.masksubpath,
                          'fsndigits': self.settings.fsndigits,
                          'prefix': self.settings.prefix,
                          'fsnlist': [f for f in sd.fsns if f not in self.settings.badfsns],
                          'ierrorprop': self.settings.ierrorprop,
                          'qerrorprop': self.settings.qerrorprop,
                          'outliermethod': self.settings.outliermethod,
                          'outlierthreshold': self.settings.outlierthreshold,
                          'cormatLogarithmic': self.settings.outlierlogcormat,
                          'qrange': self.settings.qrange,
                          'bigmemorymode': self.settings.bigmemorymode,
                          }))
        self.startTimer(100, QtCore.Qt.VeryCoarseTimer)
        self.started.emit()

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        while True:
            try:
                message: Message = self._messageQueue.get_nowait()
                jobid, samplename, distance = message.sender
            except queue.Empty:
                break
            if message.type_ == 'progress':
                self._data[jobid].progresstotal = message.totalcount
                self._data[jobid].progresscurrent = message.currentcount
                self.dataChanged.emit(self.index(jobid, 4), self.index(jobid, 4))
            elif message.type_ == 'error':
                self._data[jobid].progresstotal = message.totalcount
                self._data[jobid].progresscurrent = message.currentcount
                self._data[jobid].errormessage = message.message
                self._data[jobid].traceback = message.traceback
                self.dataChanged.emit(self.index(jobid, 0), self.index(jobid, self.columnCount()))
            else:
                raise RuntimeError(f'Unknown message type: {message.type_}')
        readies = [t for t in self._asyncresults if t.ready()]
        self._asyncresults = [t for t in self._asyncresults if t not in readies]
        for task in readies:
            result: SummaryJobResults = task.get()
            i, samplename, distance = result.jobid
            self._data[i].progresscurrent = 0
            self._data[i].progresstotal = 0
            self._data[i].spinner = None
            self.settings.addBadFSNs(result.badfsns)
            self._data[i].statusmessage='Processing done'
            self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount()))
        if ((not self._asyncresults) or ((self.status == SummarizationStatus.Stopping) and not [t for t in self._asyncresults if t.ready()])) and (self._messageQueue.empty()):
            self._pool.close()
            self._pool.join()
            self._pool = None
            self._messageQueue.join()
            self._messageQueue = None
            self._stopEvent = None
            self.killTimer(timerEvent.timerId())
            success = self.status != SummarizationStatus.Stopping
            self.status = SummarizationStatus.Idle
            self.finished.emit(success)

    def stop(self):
        if self.isIdle():
            return
        self._stopEvent.set()
        self.status = SummarizationStatus.Stopping
