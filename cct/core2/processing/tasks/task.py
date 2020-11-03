import enum
from typing import Optional, List

from PyQt5 import QtCore
import multiprocessing.synchronize, multiprocessing.queues
from ..settings import ProcessingSettings


class ProcessingStatus(enum.Enum):
    Idle = 'idle'
    Stopping = 'user stop requested'


class ProcessingTask(QtCore.QAbstractItemModel):
    finished = QtCore.pyqtSignal(bool)
    started =QtCore.pyqtSignal()
    partresult = QtCore.pyqtSignal(int, int)
    status: ProcessingStatus = ProcessingStatus.Idle
    _pool: Optional[multiprocessing.pool.Pool] = None
    _stopEvent: Optional[multiprocessing.synchronize.Event] = None
    _asyncresults: Optional[List[multiprocessing.pool.AsyncResult]] = None
    _messageQueue: Optional[multiprocessing.queues.Queue] = None
    settings: ProcessingSettings

    def __init__(self, settings: ProcessingSettings):
        self.settings = settings
        super().__init__()

    def isIdle(self) -> bool:
        return self.status == ProcessingStatus.Idle

    def isBusy(self) -> bool:
        return self.status != ProcessingStatus.Idle

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError