from PyQt5 import QtWidgets
from .project_ui import Ui_Form
from .processingwindow import ProcessingWindow


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

    def onTaskStarted(self):
        for pushbutton in [self.loadHeadersPushButton, self.averagingPushButton, self.subtractionPushButton, self.mergingPushButton]:
            pushbutton.setEnabled(False)

    def onTaskFinished(self, success: bool):
        for pushbutton in [self.loadHeadersPushButton, self.averagingPushButton, self.subtractionPushButton, self.mergingPushButton]:
            pushbutton.setEnabled(True)

    def rootPathChanged(self):
        self.project.settings.rootpath = self.rootPathLineEdit.text()
        self.project.settings.emitSettingsChanged()

    def addFSNRange(self):
        self.project.insertRow(self.project.rowCount())

    def removeFSNRange(self):
        while selectedrows := self.fsnsTreeView.selectionModel().selectedRows(0):
            self.project.removeRow(selectedrows[0].row())

    def clearFSNRanges(self):
        self.project.modelReset()

    def browseRootPath(self):
        fn = QtWidgets.QFileDialog.getExistingDirectory(
            self, 'Select measurement root directory', '')
        if not fn:
            return
        else:
            self.rootPathLineEdit.setText(fn)
            self.rootPathLineEdit.editingFinished.emit()