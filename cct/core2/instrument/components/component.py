import enum
import logging
import weakref

import h5py
from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot

from ...config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Component:
    """Logical component of an instrument"""
    config: Config
    instrument: "Instrument"
    started = Signal()
    stopped = Signal()
    stopping: bool = False
    __running: bool = False
    panicAcknowledged = Signal()

    class PanicState(enum.Enum):
        NoPanic = enum.auto()
        Panicking = enum.auto()
        Panicked = enum.auto()

    _panicking: PanicState = PanicState.NoPanic

    def __init__(self, **kwargs):  # see https://www.riverbankcomputing.com/static/Docs/PySide6/multiinheritance.html
        self.config = kwargs['config']
        if isinstance(self.config, Config):
            logger.debug('Connecting configChanged signal')
            self.config.changed.connect(self.onConfigChanged)
        if kwargs['instrument'] is not None:
            self.instrument = weakref.proxy(kwargs['instrument'])
        else:
            self.instrument = None
        self.loadFromConfig()

    @Slot(object, object)
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
        QtCore.QTimer.singleShot(0, QtCore.Qt.TimerType.VeryCoarseTimer, self.panicAcknowledged.emit)

    # noinspection PyMethodMayBeStatic
    def toNeXus(self, instrumentgroup: h5py.Group) -> h5py.Group:
        """Write NeXus-formatted information

        :param instrumentgroup: HDF5 group with NX_class == 'NXinstrument'
        :type instrumentgroup: h5py.Group instance
        """
        return instrumentgroup
