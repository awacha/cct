import logging
import weakref

from PyQt5.QtCore import pyqtSignal

from ...config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Component:
    """Logical component of an instrument"""
    config: Config
    instrument: "Instrument"
    started= pyqtSignal()
    stopped = pyqtSignal()
    stopping: bool = False
    __running: bool = False

    def __init__(self, **kwargs):  # see https://www.riverbankcomputing.com/static/Docs/PyQt5/multiinheritance.html
        #        super().__init__(**kwargs)
        logger.debug('Initializing a component')
        self.config = kwargs['config']
        self.config.changed.connect(self.onConfigChanged)
        self.instrument = weakref.proxy(kwargs['instrument'])
        logger.debug('Loading component state from the config')
        self.loadFromConfig()
        logger.debug('Initialized the component')

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
