from .processingwindow import ProcessingWindow
from .subtraction_ui import Ui_Form
from .subtractiondelegate import SubtractionDelegate
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSlot as Slot


class SubtractionWindow(ProcessingWindow, Ui_Form):
    delegate: SubtractionDelegate

    def setupUi(self, Form):
        super().setupUi(Form)
        self.progressBar.setVisible(False)
        self.treeView.setModel(self.project.subtraction)
        self.treeView.model().modelReset.connect(self.resizeTreeViewColumns)
        self.addPushButton.clicked.connect(self.addPair)
        self.removePushButton.clicked.connect(self.removePair)
        self.delegate = SubtractionDelegate(self.treeView, self.project)
        self.treeView.setItemDelegate(self.delegate)
        self.runPushButton.clicked.connect(self.onRunClicked)
        self.project.subtraction.started.connect(self.onStarted)
        self.project.subtraction.finished.connect(self.onFinished)
        self.project.subtraction.progress.connect(self.onProgress)

    @Slot()
    def resizeTreeViewColumns(self):
        for c in range(self.treeView.model().columnCount()):
            self.treeView.resizeColumnToContents(c)

    @Slot()
    def addPair(self):
        self.project.subtraction.addSubtractionPair(None, None)

    @Slot()
    def removePair(self):
        rows = reversed(sorted([i.row() for i in self.treeView.selectionModel().selectedRows(column=0)]))
        for row in rows:
            self.treeView.model().removeRow(row, parent=QtCore.QModelIndex())

    @Slot()
    def onRunClicked(self):
        if self.runPushButton.text() == 'Run':
            self.project.subtraction.start()
        elif self.runPushButton.text() == 'Stop':
            self.project.subtraction.stop()

    @Slot()
    def onStarted(self):
        self.runPushButton.setText('Stop')
        self.runPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/stop.svg')))
        self.progressBar.setVisible(True)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)

    @Slot(bool)
    def onFinished(self, success: bool):
        self.runPushButton.setText('Run')
        self.runPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
        self.progressBar.setVisible(False)
        if not success:
            QtWidgets.QMessageBox.critical(self, 'Subtraction stopped', 'Background subtraction stopped unexpectedly.')

    @Slot(int, int)
    def onProgress(self, current: int, total: int):
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(current)
