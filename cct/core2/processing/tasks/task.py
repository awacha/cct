import enum
import logging
import queue
from typing import Optional, List, Any
from configparser import ConfigParser
import weakref

from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot

import multiprocessing.synchronize, multiprocessing.queues
from ..settings import ProcessingSettings
from ..calculations.backgroundprocess import Results, Message

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ProcessingStatus(enum.Enum):
    Idle = 'idle'
    Stopping = 'user stop requested'
    Running = 'running'


class ProcessingTask(QtCore.QAbstractItemModel):
    finished = Signal(bool)
    started = Signal()
    progress = Signal(int, int)
    status: ProcessingStatus = ProcessingStatus.Idle
    _pool: Optional[multiprocessing.pool.Pool] = None
    _stopEvent: Optional[multiprocessing.synchronize.Event] = None
    _asyncresults: Optional[List[multiprocessing.pool.AsyncResult]] = None
    _messageQueue: Optional[multiprocessing.queues.Queue] = None
    _submittedtasks: int = 0
    settings: ProcessingSettings
    processing: "Processing"
    maxprocesscount: int

    def __init__(self, processing: "Processing", settings: ProcessingSettings):
        self.settings = settings
        self.processing = weakref.proxy(processing)
        self.maxprocesscount = multiprocessing.cpu_count()
        super().__init__()

    def isIdle(self) -> bool:
        return self.status.value == 'idle'

    def isBusy(self) -> bool:
        return self.status.value != 'idle'

    def start(self):
        if not self.isIdle():
            raise ValueError('Already running')
        self.status = ProcessingStatus.Running
        self._startPool()
        self._start()
        self.startTimer(100, QtCore.Qt.TimerType.PreciseTimer)
        self.started.emit()

    def stop(self):
        if self.isIdle():
            return
        self._stopEvent.set()
        self.status = ProcessingStatus.Stopping

    def _startPool(self):
        if self._pool is not None:
            raise RuntimeError('Pool already running.')
        assert self._messageQueue is None
        assert self._stopEvent is None
        assert self._asyncresults is None
        self._pool = multiprocessing.Pool(self.maxprocesscount)
        self._messageQueue = self.settings.lockManager.Queue()
        self._stopEvent = self.settings.lockManager.Event()
        self._asyncresults = []
        self._submittedtasks = 0

    def _submitTask(self, function, jobid, **kwargs):
        if self._pool is None:
            raise RuntimeError('Cannot submit tasks: pool is not running.')
        kwargs.update({
            'h5file': self.settings.filename,
            'h5lock': self.settings.h5lock,
            'jobid': jobid,
            'stopEvent': self._stopEvent,
            'messagequeue': self._messageQueue,
        })
        self._asyncresults.append(self._pool.apply_async(function, kwds=kwargs))
        self._submittedtasks += 1

    def _start(self):
        raise NotImplementedError

    def onBackgroundTaskProgress(self, jobid: Any, total: int, current: int, message: str):
        return

    def onBackgroundTaskError(self, jobid: Any, errormessage: str, traceback: str):
        logger.error(f'Error: {jobid=}, {errormessage=}, {traceback=}')
        self.progress.emit(self._submittedtasks - self.outstandingTaskCount(), self._submittedtasks)

    def onBackgroundTaskFinished(self, result: Results):
        self.progress.emit(self._submittedtasks - self.outstandingTaskCount(), self._submittedtasks)
        return None

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        while True:
            try:
                message: Message = self._messageQueue.get_nowait()
            except queue.Empty:
                break
            if message.type_ == 'progress':
                self.onBackgroundTaskProgress(message.sender, message.totalcount, message.currentcount, message.message)
            elif message.type_ == 'error':
                self.onBackgroundTaskError(message.sender, message.message, message.traceback)
                #self.onBackgroundTaskFinished(message.sender)
            elif message.type_ == 'message':
                logger.debug(f'{message.sender=}, {message.message=}')
            else:
                raise RuntimeError(f'Unknown message type: {message.type_}')
        readies = [t for t in self._asyncresults if t.ready()]
        self._asyncresults = [t for t in self._asyncresults if t not in readies]
        for task in readies:
            result: Results = task.get()
            self.onBackgroundTaskFinished(result)

        if ((not self._asyncresults) or (
                (self.status == ProcessingStatus.Stopping) and not [t for t in self._asyncresults if t.ready()])) and (
        self._messageQueue.empty()):
            self._stopPool()
            self.killTimer(timerEvent.timerId())
            success = self.status != ProcessingStatus.Stopping
            self.status = ProcessingStatus.Idle
            self.onAllBackgroundTasksFinished()
            self.finished.emit(success)

    def _stopPool(self):
        self._pool.close()
        self._pool.join()
        self._pool = None
        #            self._messageQueue.close()
        #            self._messageQueue.join_thread()
        self._messageQueue = None
        self._stopEvent = None
        self._submittedtasks = 0
        self._asyncresults = None

    def onAllBackgroundTasksFinished(self):
        pass

    def outstandingTaskCount(self) -> int:
        return len(self._asyncresults) if self._asyncresults is not None else 0
