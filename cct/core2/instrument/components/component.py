import logging
import weakref

from PyQt5.QtCore import pyqtSignal

from ...config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Component:
    """Logical component of an instrument"""
    config: Config
    instrument: "Instrument"
    started= pyqtSignal()
    stopped = pyqtSignal()
    stopping: bool = False
    __running: bool = False

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
