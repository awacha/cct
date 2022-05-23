from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSlot as Slot
from .project_ui import Ui_Form
from .processingwindow import ProcessingWindow
from ..utils.filebrowsers import getDirectory


class ProjectWindow(ProcessingWindow, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.rootPathToolButton.clicked.connect(self.browseRootPath)
        self.addFSNRangeToolButton.clicked.connect(self.addFSNRange)
        self.clearFSNRangesToolButton.clicked.connect(self.clearFSNRanges)
        self.removeFSNRangeToolButton.clicked.connect(self.removeFSNRange)
        self.rootPathLineEdit.editingFinished.connect(self.rootPathChanged)
        self.fsnsTreeView.setModel(self.project)
        self.rootPathLineEdit.setText(self.project.settings.rootpath)
        self.loadHeadersPushButton.clicked.connect(self.project.headers.start)
        self.averagingPushButton.clicked.connect(self.project.summarization.start)
        self.subtractionPushButton.clicked.connect(self.project.subtraction.start)
        self.mergingPushButton.clicked.connect(self.project.merging.start)
        for task in [self.project.headers, self.project.subtraction, self.project.summarization, self.project.merging]:
            task.started.connect(self.onTaskStarted)
            task.finished.connect(self.onTaskFinished)

    @Slot()
    def onTaskStarted(self):
        for pushbutton in [self.loadHeadersPushButton, self.averagingPushButton, self.subtractionPushButton, self.mergingPushButton]:
            pushbutton.setEnabled(False)

    @Slot(bool)
    def onTaskFinished(self, success: bool):
        for pushbutton in [self.loadHeadersPushButton, self.averagingPushButton, self.subtractionPushButton, self.mergingPushButton]:
            pushbutton.setEnabled(True)

    @Slot()
    def rootPathChanged(self):
        self.project.settings.rootpath = self.rootPathLineEdit.text()
        self.project.settings.emitSettingsChanged()

    @Slot()
    def addFSNRange(self):
        self.project.insertRow(self.project.rowCount())

    @Slot()
    def removeFSNRange(self):
        while selectedrows := self.fsnsTreeView.selectionModel().selectedRows(0):
            self.project.removeRow(selectedrows[0].row())

    @Slot()
    def clearFSNRanges(self):
        self.project.modelReset()

    @Slot()
    def browseRootPath(self):
        dn = getDirectory(self, 'Select measurement root directory', '')
        if not dn:
            return
        self.rootPathLineEdit.setText(dn)
        self.rootPathLineEdit.editingFinished.emit()
