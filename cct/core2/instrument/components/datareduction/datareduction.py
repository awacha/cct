import logging
import multiprocessing
import queue
from typing import Optional

from PyQt5 import QtCore

from .datareductionpipeline import DataReductionPipeLine
from ..component import Component
from ....dataclasses import Exposure

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger_background = logging.getLogger(__name__ + ':background')
logger.setLevel(logging.DEBUG)


class DataReduction(QtCore.QObject, Component):
    backend: Optional[multiprocessing.Process] = None
    queuetobackend: multiprocessing.Queue = None
    queuefrombackend: multiprocessing.Queue = None
    datareductionresult= QtCore.pyqtSignal(object)
    submitted: int = 0
    timerinterval: float = 0.1
    timer: Optional[int] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _startbackend(self):
        if self.backend is not None:
            raise RuntimeError('Data reduction pipeline already running.')
        self.queuetobackend = multiprocessing.Queue()
        self.queuefrombackend = multiprocessing.Queue()
        self.backend = multiprocessing.Process(target=DataReductionPipeLine.run_in_background,
                                               args=(self.config.asdict(), self.queuetobackend, self.queuefrombackend))
        self.backend.start()

    def startComponent(self):
        self._startbackend()
        self.started.emit()

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        try:
            cmd, arg = self.queuefrombackend.get_nowait()
        except queue.Empty:
            return
        logger.debug(f'Message from backend: {cmd=}, {arg=}')
        if cmd == 'finished' and self.stopping:
            self.killTimer(self.timer)
            self.timer = None
            self.backend = None
            self.stopping = False
            self.stopped.emit()
        elif cmd == 'finished':
            # stopped for other reasons, try to restart.
            self.backend = None
            self._startbackend()
        elif cmd == 'log':
            logger_background.log(*arg)
        elif cmd == 'result':
            self.datareductionresult.emit(arg)
            self.submitted -= 1
        else:
            assert False
        if self.submitted <= 0:
            self.submitted = 0
            self.queuetobackend.put_nowait(('end', None))
#            self.killTimer(self.timer)

    def stopComponent(self):
        self.stopping = True
        self.queuetobackend.put_nowait(('end', None))
        if self.timer is None:
            self.timer = self.startTimer(0, QtCore.Qt.VeryCoarseTimer)

    def running(self) -> bool:
        return self.backend is not None

    def submit(self, exposure: Exposure):
        if not self.running():
            raise RuntimeError('Cannot submit exposure: data reduction component not running')
        self.queuetobackend.put_nowait(('process', exposure))
        if self.timer is None:
            self.timer = self.startTimer(int(self.timerinterval * 1000), QtCore.Qt.VeryCoarseTimer)
        self.submitted += 1

    def onConfigChanged(self, path, value):
        if self.running():
            self.queuetobackend.put_nowait(('config', self.config.asdict()))
