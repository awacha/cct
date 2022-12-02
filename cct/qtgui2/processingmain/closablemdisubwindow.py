import logging

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Signal

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ClosableMdiSubWindow(QtWidgets.QMdiSubWindow):
    hidden = Signal(QtWidgets.QWidget)

    def closeEvent(self, closeEvent: QtGui.QCloseEvent) -> None:
        logger.debug(f'ClosableMdiSubWindow got a close event. '
                     f'Hiding window, not closing. '
                     f'{self.objectName()=}, {self.widget().objectName()=}, {type(self.widget())=}')
        self.hidden.emit(self.widget())
        self.hide()
        closeEvent.ignore()
