"""Interface class for the background processing task"""
import logging
import queue
from multiprocessing import Queue, Lock, Event, Manager, cpu_count
from multiprocessing.pool import AsyncResult, Pool
from typing import Sequence, Optional, List, Any, Dict

import numpy as np
from PyQt5 import QtCore, QtGui
from sastool.classes2 import Header

from .h5reader import H5Reader
from ..config import Config
from ...core.processing import ProcessingJob, Message, ProcessingJobResults

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def processSingleSampleSingleDistance(jobid: int, fsns: List[int], badfsns: List[int], configdict: Dict,
                                      h5WriterLock: Lock,
                                      messageQueue: Queue, killSwitch: Event):
    if configdict['autoq']:
        qrange = None
    elif configdict['customqlogscale']:
        qrange = np.logspace(np.log10(configdict['customqmin']), np.log10(configdict['customqmax']),
                             configdict['customqcount'])
    else:
        qrange = np.linspace(configdict['customqmin'], configdict['customqmax'], configdict['customqcount'])
    job = ProcessingJob(jobid=jobid, h5writerLock=h5WriterLock,
                        killswitch=killSwitch,
                        resultsqueue=messageQueue,
                        rootdir=configdict['datadir'],
                        fsnlist=fsns, badfsns=badfsns,
                        h5file=configdict['hdf5'],
                        ierrorprop=configdict['errorpropagation'],
                        qerrorprop=configdict['abscissaerrorpropagation'],
                        outliermethod=configdict['outliermethod'],
                        outliermultiplier=configdict['std_multiplier'],
                        logcmat=configdict['logcorrelmatrix'],
                        qrange=qrange,
                        bigmemorymode=False,
                        )
    job.run()
    return job.result


class JobRecord:
    samplename: str
    distance: float
    temperature: Optional[float]
    fsns: List[int]
    total: int = 0
    current: int = 0
    statusmessage: str = 'Not yet processed'
    asyncresult: AsyncResult = None
    errormessage: Optional[str] = None
    enabled: bool = True
    killswitch: Event = None
    messageQueue: Queue = None
    lastProcessingResult: ProcessingJobResults = None

    def __init__(self, samplename: str, distance: float, temperature: Optional[float], fsns: Sequence[int],
                 lockmanager: Manager):
        self.samplename = samplename
        self.distance = distance
        self.temperature = temperature
        self.fsns = list(fsns)
        self.killswitch = lockmanager.Event()
        self.messageQueue = lockmanager.Queue()

    @property
    def running(self) -> bool:
        if self.asyncresult is None:
            return False
        else:
            return not self.asyncresult.ready()


class Processor(QtCore.QAbstractItemModel):
    """A front-end and scheduler for background data processing jobs.

    This is implemented as an item model, to be used in treeviews.

    Columns are:
        0: sample name (user checkable)
        1: distance
        2: temperature
        3: number of exposures
        4: progress bar
    """

    TIMERINTERVAL: int = 100  # milliseconds, calling the check
    TEMPERATURETOLERANCE: float = 0.5  # ToDo: make this a config item
    MAXMESSAGESTOREADATONCE: int = 100  # read at most this many messages from the message queue, do not hog the main loop
    _pool: Optional[Pool]
    _jobs: List[JobRecord]
    _h5WriterLock: Lock = None
    _headers: List[Header]
    _messageQueue: Queue = None
    finished = QtCore.pyqtSignal()  # processing finished
    _timerid: int = 0
    config: Config = None
    classifyByTemperature: bool = False  # ToDo: make this some kind of property
    _lockManager: Manager = None
    _h5reader: H5Reader = None

    def __init__(self, config: Config, project: "Project"):
        super().__init__()
        self.config = config
        self.project = project
        self.config.configItemChanged.connect(self.onConfigChanged)
        self._lockManager = Manager()
        self._h5WriterLock = self._lockManager.Lock()
        self._h5reader = H5Reader(config.hdf5)
        self._headers = []
        self._startPool()

    def _startPool(self):
        self._pool = Pool(min(self.config.maxjobs, cpu_count()))
        self._recreateJobs()
        self._messageQueue = Queue()

    def _stopPool(self, terminate: bool = False):
        if terminate:
            self._pool.terminate()
        else:
            self._pool.close()
        self._pool.join()

    def isBusy(self) -> bool:
        return bool([j for j in self._jobs if j.running])

    def setHeaders(self, headers: Sequence[Header]):
        if self.isBusy():
            raise RuntimeError('Cannot change the headers while busy.')
        self._headers = list(headers)  # make a copy
        self._recreateJobs()

    def _recreateJobs(self):
        self.beginResetModel()
        self._jobs = []
        try:
            for title in sorted({h.title for h in self._headers}):
                for distance in sorted({float(h.distance) for h in self._headers if h.title == title}):
                    if self.classifyByTemperature:
                        temperatures = {}
                        for h in self._headers:
                            if h.title != title or float(h.distance) != distance:
                                continue
                            if h.temperature is None:
                                try:
                                    temperatures[None].append(h)
                                except KeyError:
                                    temperatures[None] = [h]
                            else:
                                # find the nearest temperature
                                try:
                                    nearest = sorted([k for k in temperatures if (k is not None) and
                                                      abs(float(h.temperature) - k) <= self.TEMPERATURETOLERANCE],
                                                     key=lambda k: abs(float(h.temperature) - k))[0]
                                    temperatures[nearest].append(h)
                                except IndexError:
                                    temperatures[float(h.temperature)] = [h]
                        for temp in temperatures:
                            self._jobs.append(JobRecord(title, distance, temp, [h.fsn for h in temperatures[temp]],
                                                        lockmanager=self._loc
                                                        ))
                    else:
                        self._jobs.append(JobRecord(title, distance, None,
                                                    [h.fsn for h in self._headers
                                                     if h.title == title
                                                     and float(h.distance) == float(distance)],
                                                    lockmanager=self._lockManager))
        finally:
            self.endResetModel()

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if index.column() == 0 and role == QtCore.Qt.CheckStateRole:
            return [QtCore.Qt.Unchecked, QtCore.Qt.Checked][self._jobs[index.row()].enabled]
        elif role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return self._jobs[index.row()].samplename
            elif index.column() == 1:
                return '{:.2f}'.format(self._jobs[index.row()].distance)
            elif index.column() == 2:
                return '{:.2f}°C'.format(self._jobs[index.row()].temperature) \
                    if self._jobs[index.row()].temperature is not None else '--'
            elif index.column() == 3:
                return '{:d}'.format(len(self._jobs[index.row()].fsns))
            elif index.column() == 4:
                return self._jobs[index.row()].statusmessage if self._jobs[index.row()].errormessage is None else \
                    self._jobs[index.row()].errormessage  # the custom item delegate takes care of this
        elif role == QtCore.Qt.BackgroundRole:
            if self._jobs[index.row()].errormessage is not None:
                return QtGui.QBrush(QtGui.QColor('red'))
            else:
                return None
        elif role == QtCore.Qt.ToolTipRole:
            return self._jobs[index.row()].errormessage
        elif role == QtCore.Qt.UserRole:
            return self._jobs[index.row()]
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if index.column() == 0 and role == QtCore.Qt.CheckStateRole:
            self._jobs[index.row()].enabled = (value == QtCore.Qt.Checked)
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount()),
                                  [QtCore.Qt.DisplayRole, QtCore.Qt.CheckStateRole])
            return True
        return False

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 5

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._jobs)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if (index.column() == 0) and not self.isBusy():
            # if we are idle, allow the user to check/uncheck the first column.
            return QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | \
                   QtCore.Qt.ItemNeverHasChildren
        else:
            return QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Sample name', 'Distance', 'Temperature', 'Count', 'Status'][section]
        return None

    def start(self):
        logger.debug('Starting processor.')
        for row, j in enumerate(self._jobs):
            if not j.enabled:
                continue
            j.statusmessage = 'Waiting...'
            j.errormessage = None
            j.asyncresult = self._pool.apply_async(
                processSingleSampleSingleDistance,
                kwds={'jobid': row, 'fsns': j.fsns,
                      'badfsns': self.project.badfsns,
                      'configdict': self.config.toDict(),
                      'h5WriterLock': self._h5WriterLock,
                      'messageQueue': j.messageQueue,
                      'killSwitch': j.killswitch})
            logger.debug('Submitted job {}'.format(row))
        # emit a dataChanged over the whole table: this updates status to a progress bar where needed, as well as
        # disables checking/unchecking while the process is running
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount(), self.columnCount()))
        self._timerid = self.startTimer(self.TIMERINTERVAL)

    def stop(self):
        """Stop processing"""
        for j in self._jobs:
            j.killswitch.set()

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        # check for messages in the message queue
        for i in range(self.MAXMESSAGESTOREADATONCE):  # do not hog the main loop
            messagesread = False
            for row, j in enumerate(self._jobs):
                try:
                    message = j.messageQueue.get_nowait()
                    #                    logger.debug('Message received for job {}: {}'.format(row, message))
                    messagesread = True
                except queue.Empty:
                    # there are no messages waiting.
                    continue
                assert isinstance(message, Message)
                if message.type_ == 'progress':
                    self._jobs[message.sender].total = message.totalcount
                    self._jobs[message.sender].current = message.currentcount
                    self._jobs[message.sender].statusmessage = message.message
                #                    self.dataChanged.emit(self.index(message.sender, 0),
                #                                          self.index(message.sender, self.columnCount()),
                #                                          [QtCore.Qt.DisplayRole])
                elif message.type_ == 'error':
                    logger.debug('Error message received for job {}: {} (traceback: {})'.format(row, message.message, message.traceback))
                    self._jobs[message.sender].errormessage = message.traceback
                    self._jobs[message.sender].statusmessage = message.message
                #                    self.dataChanged.emit(self.index(message.sender, 0),
                #                                          self.index(message.sender, self.columnCount()),
                #                                          [QtCore.Qt.DisplayRole, QtCore.Qt.ToolTipRole, QtCore.Qt.BackgroundRole])
                else:
                    raise ValueError(message.type_)
            if not messagesread:
                break
        for j in self._jobs:
            if (j.asyncresult is not None) and j.asyncresult.ready():
                j.lastProcessingResult = j.asyncresult.get()
                j.statusmessage = 'Finished in {:.2f} seconds.'.format(j.lastProcessingResult.time_total)
                j.asyncresult = None
                if j.lastProcessingResult.success:
                    self.project.addBadFSNs(j.lastProcessingResult.badfsns)
        if not [j for j in self._jobs if j.asyncresult is not None]:
            # all jobs are finished: stop the timer and notify about the finish. The pool is kept running.
            self.killTimer(self._timerid)
            self.finished.emit()
        # emit an all-over dataChanged signal to keep all progress bars scrolling
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount(), self.columnCount()))
        event.accept()

    def onConfigChanged(self, section: str, item: str, newvalue: Any):
        if item == 'maxjobs':
            self._stopPool()
            self._startPool()

    def newBadFSNs(self) -> List[int]:
        ret = []
        for j in self._jobs:
            if j.lastProcessingResult.success:
                ret.extend(j.lastProcessingResult.badfsns)
        return ret
