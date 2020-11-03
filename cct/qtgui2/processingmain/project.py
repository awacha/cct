from PyQt5 import QtWidgets
from .project_ui import Ui_Form
from .processingwindow import ProcessingWindow


class ProjectWindow(ProcessingWindow, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.h5FileToolButton.clicked.connect(self.browseH5File)
        self.rootPathToolButton.clicked.connect(self.browseRootPath)
        self.badFSNsToolButton.clicked.connect(self.browseBadFSNsFile)
        self.addFSNRangeToolButton.clicked.connect(self.addFSNRange)
        self.clearFSNRangesToolButton.clicked.connect(self.clearFSNRanges)
        self.removeFSNRangeToolButton.clicked.connect(self.removeFSNRange)
        self.h5FileLineEdit.editingFinished.connect(self.h5FileChanged)
        self.badFSNsLineEdit.editingFinished.connect(self.badFSNsChanged)
        self.rootPathLineEdit.editingFinished.connect(self.rootPathChanged)
        self.fsnsTreeView.setModel(self.project)

    def rootPathChanged(self):
        self.project.settings.rootpath = self.rootPathLineEdit.text()

    def badFSNsChanged(self):
        self.project.settings.badfsnsfile = self.badFSNsLineEdit.text()
        self.project.settings.loadBadFSNs()

    def h5FileChanged(self):
        self.project.settings.h5filename = self.h5FileLineEdit.text()

    def addFSNRange(self):
        self.project.insertRow(self.project.rowCount())

    def removeFSNRange(self):
        while selectedrows := self.fsnsTreeView.selectionModel().selectedRows(0):
            self.project.removeRow(selectedrows[0].row())

    def clearFSNRanges(self):
        self.project.modelReset()

    def browseH5File(self):
        fn, fltr = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Select HDF5 file which stores the results', '', 'HDF5 files (*.h5);;All files(*)', 'HDF5 files (*.h5)')
        if not fn:
            return
        else:
            self.h5FileLineEdit.setText(fn)
            self.h5FileLineEdit.editingFinished.emit()

    def browseBadFSNsFile(self):
        fn, fltr = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Select file to store bad file sequence numbers', '', 'Text files (*.txt);;All files(*)', 'Text files (*.txt)')
        if not fn:
            return
        else:
            self.badFSNsLineEdit.setText(fn)
            self.badFSNsLineEdit.editingFinished.emit()

    def browseRootPath(self):
        fn = QtWidgets.QFileDialog.getExistingDirectory(
            self, 'Select measurement root directory', '')
        if not fn:
            return
        else:
            self.rootPathLineEdit.setText(fn)
            self.rootPathLineEdit.editingFinished.emit()


