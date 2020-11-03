from .processingwindow import ProcessingWindow
from .headers_ui import Ui_Form
from PyQt5 import QtGui


class HeadersWindow(ProcessingWindow, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.project.headers)
        self.reloadPushButton.clicked.connect(self.startStopReload)
        self.project.headers.finished.connect(self.onFinished)
        self.project.headers.started.connect(self.onStarted)

    def startStopReload(self):
        if self.reloadPushButton.text() == 'Stop':
            self.project.headers.stop()
        else:
            self.project.reloadHeaders()

    def onFinished(self):
        self.reloadPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap('icons:/start.svg')))
        self.reloadPushButton.setText('(Re)load')

    def onStarted(self):
        self.reloadPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap('icons:/stop.svg')))
        self.reloadPushButton.setText('Stop')