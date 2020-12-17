from .processingwindow import ProcessingWindow
from .headers_ui import Ui_Form
from PyQt5 import QtGui, QtCore

import logging
logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HeadersWindow(ProcessingWindow, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.project.headers)
        self.reloadPushButton.clicked.connect(self.startStopReload)
        self.project.headers.finished.connect(self.onFinished)
        self.project.headers.started.connect(self.onStarted)
        self.project.headers.progress.connect(self.onProgress)
        self.markBadToolButton.clicked.connect(self.markSelectedAsGoodOrBad)
        self.markGoodToolButton.clicked.connect(self.markSelectedAsGoodOrBad)
        self.progressBar.setVisible(False)
        # Do not resize treeview columns automatically: if a lot of headers are loaded, it takes too much time!
        #self.treeView.model().modelReset.connect(self.resizeTreeViewColumns)

    def resizeTreeViewColumns(self):
        logger.debug('Resize treeview columns')
        for c in range(self.treeView.model().columnCount()):
            self.treeView.resizeColumnToContents(c)
        logger.debug('Treeview columns resized.')

    def markSelectedAsGoodOrBad(self):
        for selectedindex in self.treeView.selectionModel().selectedRows(0):
            self.project.headers.setData(
                index=selectedindex,
                value=QtCore.Qt.Checked if self.sender() is self.markBadToolButton else QtCore.Qt.Unchecked,
                role=QtCore.Qt.CheckStateRole)

    def startStopReload(self):
        if self.reloadPushButton.text() == 'Stop':
            self.project.headers.stop()
        else:
            self.project.headers.start()

    def onFinished(self):
        self.reloadPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
        self.reloadPushButton.setText('(Re)load')
        self.progressBar.setVisible(False)

    def onStarted(self):
        self.reloadPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/stop.svg')))
        self.reloadPushButton.setText('Stop')
        self.progressBar.setVisible(True)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)

    def onProgress(self, current: int, total: int):
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(current)
