"""Interface class for the background processing task"""
import logging
import queue
import time
from multiprocessing import Queue, Event, Manager, cpu_count
from multiprocessing.pool import AsyncResult, Pool
from typing import Optional, List, Any

from PyQt5 import QtCore, QtGui

from ...core.processing import Message

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class JobRecord:
    """This is how the background runner keeps track of jobs: to be submitted, running and completed as well."""
    statusmessage: str = 'Not yet processed'
    total: int = 0
    current: int = 0
    asyncresult: Optional[AsyncResult] = None
    errormessage: Optional[str] = None
    enabled: bool = True
    killswitch: Event = None
    messageQueue: Queue = None
    lastProcessingResult = None

    def __init__(self, lockmanager: Manager):
        self.killswitch = lockmanager.Event()
        self.messageQueue = lockmanager.Queue()

    @property
    def isRunning(self) -> bool:
        if self.asyncresult is None:
            return False
        else:
            return not self.asyncresult.ready()

    @property
    def toBeReaped(self) -> bool:
        return (self.asyncresult is not None) and self.asyncresult.ready()

    @property
    def finished(self) -> bool:
        return self.asyncresult is None

    def submit(self, jobid: int, pool:Pool, project: "Project"):
        raise NotImplementedError

    def reap(self, project:"Project"):
        raise NotImplementedError

class BackgroundRunner(QtCore.QAbstractItemModel):
    """A front-end and scheduler for background data processing jobs.

    This is implemented as an item model, to be used in treeviews.

    """

    timerInterval: int = 200  # milliseconds, calling the check
    maxReadMsgCount: int = 1  # read at most this many messages from the message queue, do not hog the main loop
    TEMPERATURETOLERANCE: float = 0.5  # ToDo: make this a config item
    _pool: Optional[Pool]
    _columnnames: List[str]
    _jobs: List[JobRecord]
    _runningjobs: List[JobRecord]
    finished = QtCore.pyqtSignal()  # processing finished
    _timerid: int = 0
    classifyByTemperature: bool = False  # ToDo: make this some kind of property

    def __init__(self, project: "Project"):
        super().__init__()
        self._jobs = []
        self._runningjobs = []
        self.project = project
        self.project.config.configItemChanged.connect(self.onConfigChanged)
        self._startPool()

    def _startPool(self):
        self._pool = Pool(min(self.project.config.maxjobs, cpu_count()))
        self._recreateJobs()

    def _stopPool(self, terminate: bool = False):
        if terminate:
            self._pool.terminate()
        else:
            self._pool.close()
        self._pool.join()

    def isBusy(self) -> bool:
        return bool([j for j in self._jobs if j.isRunning])

    def _recreateJobs(self):
        raise NotImplementedError

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if index.column() == 0 and role == QtCore.Qt.CheckStateRole:
            return [QtCore.Qt.Unchecked, QtCore.Qt.Checked][self._jobs[index.row()].enabled]
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
        return len(self._columnnames)

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
            return self._columnnames[section]
        return None

    def start(self):
        logger.debug('Starting background processor.')
        for row, j in enumerate(self._jobs):
            if not j.enabled:
                continue
            j.statusmessage = 'Waiting...'
            j.errormessage = None
            j.submit(row, self._pool, self.project)
            if j.isRunning:
                self._runningjobs.append(j)
            logger.debug('Submitted job {}'.format(row))
        # emit a dataChanged over the whole table: this updates status to a progress bar where needed, as well as
        # disables checking/unchecking while the process is running
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount(), self.columnCount()))
        self._timerid = self.startTimer(self.timerInterval)

    def stop(self):
        """Stop processing"""
        for j in self._jobs:
            j.killswitch.set()

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        # check for messages in the message queue
        t0 = time.monotonic()
        for i in range(self.maxReadMsgCount):  # do not hog the main loop
            messagesread = False
            for row, j in enumerate(self._runningjobs):
                try:
                    message = j.messageQueue.get_nowait()
                    messagesread = True
                except queue.Empty:
                    # there are no messages waiting.
                    continue
                assert isinstance(message, Message)
                if message.type_ == 'progress':
                    self._jobs[message.sender].total = message.totalcount
                    self._jobs[message.sender].current = message.currentcount
                    self._jobs[message.sender].statusmessage = message.message
                elif message.type_ == 'error':
                    logger.debug('Error message received for job {}: {} (traceback: {})'.format(row, message.message, message.traceback))
                    self._jobs[message.sender].errormessage = message.traceback
                    self._jobs[message.sender].statusmessage = message.message
                else:
                    raise ValueError(message.type_)
            if not messagesread:
                break
        for j in self._runningjobs:
            if j.toBeReaped:
                j.reap(self.project)
                self._runningjobs.remove(j)
        if not self._runningjobs:
            # all jobs are finished: stop the timer and notify about the finish. The pool is kept running.
            self.killTimer(self._timerid)
            self.finished.emit()
        # emit an all-over dataChanged signal to keep all progress bars scrolling
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount(), self.columnCount()))
        event.accept()
        logger.debug('Time spent in timerEvent: {:.3f} sec'.format(time.monotonic() - t0))

    def onConfigChanged(self, section: str, item: str, newvalue: Any):
        if item == 'maxjobs':
            self._stopPool()
            self._startPool()
