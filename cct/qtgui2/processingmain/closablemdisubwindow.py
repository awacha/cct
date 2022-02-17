import logging

from PyQt5 import QtWidgets, QtGui, QtCore

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ClosableMdiSubWindow(QtWidgets.QMdiSubWindow):
    hidden = QtCore.pyqtSignal(QtWidgets.QWidget)

    def closeEvent(self, closeEvent: QtGui.QCloseEvent) -> None:
        logger.debug(f'ClosableMdiSubWindow got a close event. '
                     f'Hiding window, not closing. '
                     f'{self.objectName()=}, {self.widget().objectName()=}, {type(self.widget())=}')
        self.hidden.emit(self.widget())
        self.hide()
        closeEvent.ignore()
