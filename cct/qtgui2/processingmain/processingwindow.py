from PyQt5 import QtWidgets, QtGui, QtCore

from ...core2.processing.processing import Processing


class ProcessingWindow(QtWidgets.QWidget):
    project: Processing

    def __init__(self, project: Processing):
        super().__init__()
        self.project = project
        self.setupUi(self)
        self.destroyed.connect(self.onDestroyed)

    def closeEvent(self, closeEvent: QtGui.QCloseEvent) -> None:
        self.showMinimized()
        closeEvent.ignore()

    def onDestroyed(self, object: QtCore.QObject):
        pass


