import logging
import multiprocessing
import queue
from typing import Optional

from PySide6 import QtCore
from PySide6.QtCore import Signal

from .datareductionpipeline import DataReductionPipeLine
from ..component import Component
from ....dataclasses import Exposure

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

logger_background = logging.getLogger(__name__ + ':background')
logger.setLevel(logging.INFO)


class DataReduction(Component, QtCore.QObject):
    backend: Optional[multiprocessing.Process] = None
    queuetobackend: Optional[multiprocessing.Queue] = None
    queuefrombackend: Optional[multiprocessing.Queue] = None
    datareductionresult = Signal(object)
    submitted: int = 0
    timerinterval: float = 0.1
    configsenddelay: float = 0.5
    _configsendtimer: Optional[int] = None
    timer: Optional[int] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _startbackend(self):
        if self.backend is not None:
            raise RuntimeError('Data reduction pipeline already running.')
        self.queuetobackend = multiprocessing.Queue()
        self.queuefrombackend = multiprocessing.Queue()
        self.backend = multiprocessing.Process(target=DataReductionPipeLine.run_in_background,
                                               args=(self.cfg.toDict(), self.queuetobackend, self.queuefrombackend))
        self.backend.start()

    def _cleanupbackend(self):
        if self.backend is None:
            return
        self.queuetobackend.close()
        self.queuefrombackend.close()
        self.backend.join()
        self.queuetobackend = None
        self.queuefrombackend = None
        self.backend = None
        self.killTimer(self.timer)
        self.timer = None
        self.stopping = False

    def startComponent(self):
        self._startbackend()
        self.started.emit()

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        if event.timerId() == self.timer:
            try:
                cmd, arg = self.queuefrombackend.get_nowait()
            except queue.Empty:
                return
            logger.debug(f'Message from backend: {cmd=}, {arg=}')
            if cmd == 'finished' and self.stopping:
                self._cleanupbackend()
                self.stopped.emit()
            elif cmd == 'finished':
                # stopped for other reasons, try to restart.
                self._cleanupbackend()
                self._startbackend()
            elif cmd == 'log':
                logger_background.log(*arg)
            elif cmd == 'result':
                self.datareductionresult.emit(arg)
                self.submitted -= 1
            else:
                assert False
            if (self.submitted <= 0) and (cmd != 'log'):
                self.submitted = 0
                if self.timer is not None:
                    self.killTimer(self.timer)
                    self.timer = None
                # keep the back-end running but we do not expect any message from it.
                if self._panicking == self.PanicState.Panicking:
                    super().panichandler()
        elif event.timerId() == self._configsendtimer:
            logger.debug('Sending config to backend')
            self.queuetobackend.put_nowait(('config', self.cfg.toDict()))
            self.killTimer(self._configsendtimer)
            self._configsendtimer = None

    def stopComponent(self):
        self.stopping = True
        self.queuetobackend.put_nowait(('end', None))
        if self.timer is None:
            self.timer = self.startTimer(10, QtCore.Qt.TimerType.VeryCoarseTimer)

    def running(self) -> bool:
        return self.backend is not None

    def submit(self, exposure: Exposure):
        if self._panicking != self.PanicState.NoPanic:
            raise RuntimeError('Cannot submit exposure: panic!')
        if not self.running():
            raise RuntimeError('Cannot submit exposure: data reduction component not running')
        self.queuetobackend.put_nowait(('process', exposure))
        if self.timer is None:
            self.timer = self.startTimer(int(self.timerinterval * 1000), QtCore.Qt.TimerType.VeryCoarseTimer)
        self.submitted += 1

    def onConfigChanged(self, path, value):
        if self.running():
            if self._configsendtimer is not None:
                self.killTimer(self._configsendtimer)
            self._configsendtimer = self.startTimer(int(self.configsenddelay * 1000), QtCore.Qt.TimerType.PreciseTimer)

    def panichandler(self):
        self._panicking = self.PanicState.Panicking
        if self.submitted > 0:
            pass
        else:
            super().panichandler()
