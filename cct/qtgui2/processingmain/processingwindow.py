import weakref

from PyQt5 import QtWidgets, QtGui, QtCore

from ...core2.processing.processing import Processing


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
            closeEvent.accept()
        else:
            self.showMinimized()
            closeEvent.ignore()

    def onDestroyed(self, object: QtCore.QObject):
        pass


