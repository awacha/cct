from PyQt5 import QtWidgets, QtGui, QtCore
import logging

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ClosableMdiSubWindow(QtWidgets.QMdiSubWindow):
    hidden = QtCore.pyqtSignal(QtWidgets.QWidget)

    def closeEvent(self, closeEvent: QtGui.QCloseEvent) -> None:
        logging.debug(f'ClosableMdiSubWindow got a close event. {self.objectName()=}, {self.widget().objectName()=}, {type(self.widget())=}')
        self.hidden.emit(self.widget())
        self.hide()
        closeEvent.ignore()
