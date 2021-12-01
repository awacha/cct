import enum
import logging
import weakref

from PyQt5 import QtCore

from ...config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Component:
    """Logical component of an instrument"""
    config: Config
    instrument: "Instrument"
    started= QtCore.pyqtSignal()
    stopped = QtCore.pyqtSignal()
    stopping: bool = False
    __running: bool = False
    panicAcknowledged = QtCore.pyqtSignal()

    class PanicState(enum.Enum):
        NoPanic = enum.auto()
        Panicking = enum.auto()
        Panicked = enum.auto()

    _panicking: PanicState = PanicState.NoPanic

    def __init__(self, **kwargs):  # see https://www.riverbankcomputing.com/static/Docs/PyQt5/multiinheritance.html
        self.config = kwargs['config']
        if isinstance(self.config, Config):
            self.config.changed.connect(self.onConfigChanged)
        if kwargs['instrument'] is not None:
            self.instrument = weakref.proxy(kwargs['instrument'])
        else:
            self.instrument = None
        self.loadFromConfig()

    def onConfigChanged(self, path, value):
        pass

    def saveToConfig(self):
        pass

    def loadFromConfig(self):
        pass

    def startComponent(self):
        self.__running = True
        self.started.emit()

    def stopComponent(self):
        self.stopping = True
        self.__running = False
        self.stopped.emit()

    def running(self) -> bool:
        return self.__running

    def panichandler(self):
        """Default panic handler: schedules the emission of the panicAcknowledged signal soon afterwards."""
        self._panicking = self.PanicState.Panicked
        QtCore.QTimer.singleShot(0, QtCore.Qt.VeryCoarseTimer, self.panicAcknowledged.emit)