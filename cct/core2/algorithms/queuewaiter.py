import logging
import traceback
from multiprocessing.queues import Queue
from queue import Empty
from typing import Callable, Tuple, List, Union, Optional, ClassVar

from PyQt5 import QtCore

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class QueueWaiter(QtCore.QObject):
    """A Qt event source for multiprocessing queues"""
    queues: List[Tuple[Queue, Callable]]
    timerid: Optional[int] = None
    timerinterval: int
    _instance: ClassVar["QueueWaiter"]

    def __init__(self, timerinterval: int = 0):
        if not hasattr(type(self), '_instance'):
            type(self)._instance = self
        self.queues = []
        self.timerid = None
        self.timerinterval = timerinterval
        super().__init__()

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        for queue, callback in self.queues:
            try:
                message = queue.get_nowait()
            except Empty:
                continue
            try:
                callback(message)
            except Exception as exc:
                logger.critical(f'Exception in queue callback: {exc}, {traceback.format_exc()}')

    def registerQueue(self, queue: Queue, callback: Callable):
        if queue in [q for q, cb in self.queues]:
            raise ValueError('Queue already registered')
        logger.debug(f'Registering {queue=}, {callback=}')
        self.queues.append((queue, callback))
        if not self.timerid:
            # timer is not running, start it.
            self.timerid = self.startTimer(self.timerinterval, QtCore.Qt.PreciseTimer)

    def deregisterQueue(self, queueorcallback: Union[Queue, Callable]):
        logger.debug(f'Deregistering {queueorcallback=}')
        self.queues = [(q, cb) for q, cb in self.queues if not ((q is queueorcallback) or (cb is queueorcallback))]
        logger.debug(f'Remaining queues: {len(self.queues)}')
        if not self.queues:
            self.killTimer(self.timerid)
            self.timerid = None

    @classmethod
    def instance(cls) -> "QueueWaiter":
        if not hasattr(cls, '_instance'):
            return cls()
        else:
            return cls._instance
