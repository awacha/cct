import weakref
import logging

from PyQt5 import QtWidgets, QtGui, QtCore

from ...core2.processing.processing import Processing

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ProcessingWindow(QtWidgets.QWidget):
    project: Processing
    mainwindow: "Main"
    closable: bool

    def __init__(self, project: Processing, mainwindow: "Main", closable: bool=False):
        super().__init__()
        self.closable = closable
        self.project = project
        try:
            self.mainwindow = weakref.proxy(mainwindow)
        except TypeError:
            self.mainwindow = mainwindow  # already a weakref proxy
        self.setupUi(self)
        self.destroyed.connect(self.onDestroyed)

    def closeEvent(self, closeEvent: QtGui.QCloseEvent) -> None:
        if self.closable:
            logger.debug(f'Closing a processing window {self.objectName()=}')
            closeEvent.accept()
        else:
            logger.debug(f'Minimizing a processing window instead of closing {self.objectName()=}')
            self.showMinimized()
            closeEvent.ignore()

    def onDestroyed(self, object: QtCore.QObject):
        logger.debug('A processing window has been destroyed')
        pass


