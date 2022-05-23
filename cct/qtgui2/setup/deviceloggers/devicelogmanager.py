from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSlot as Slot

from .devicelogmanager_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from .startstopdelegate import StartStopDelegate
from ...utils.filebrowserdelegate import FileSelectorDelegate


class DeviceLogManagerUI(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.devicelogmanager)
        self.addToolButton.clicked.connect(self.onAddClicked)
        self.removeToolButton.clicked.connect(self.onRemoveClicked)
        self.clearToolButton.clicked.connect(self.onClearClicked)
        self.startToolButton.clicked.connect(self.onStartAllClicked)
        self.stopToolButton.clicked.connect(self.onStopAllClicked)
        self.treeView.setItemDelegateForColumn(4, StartStopDelegate(self.treeView))
        fsd = FileSelectorDelegate(self.treeView)
        fsd.setFilter('Log files (*.log);;All files(*)')
        fsd.setDefaultFilter('Log files (*.log)')
        fsd.setMode(fsd.Mode.SaveFile)
        fsd.setCaption('Select file to save the log to...')
        self.treeView.setItemDelegateForColumn(1, fsd)

    @Slot()
    def onAddClicked(self):
        self.instrument.devicelogmanager.insertRow(self.instrument.devicelogmanager.rowCount(QtCore.QModelIndex()),
                                                   QtCore.QModelIndex())

    @Slot()
    def onRemoveClicked(self):
        for row in reversed(sorted({index.row() for index in self.treeView.selectionModel().selectedRows(0)})):
            self.instrument.devicelogmanager.removeRow(row, QtCore.QModelIndex())

    @Slot()
    def onClearClicked(self):
        self.instrument.devicelogmanager.removeRows(0, self.instrument.devicelogmanager.rowCount(QtCore.QModelIndex()),
                                                    QtCore.QModelIndex())

    @Slot()
    def onStartAllClicked(self):
        self.instrument.devicelogmanager.startAll()

    @Slot()
    def onStopAllClicked(self):
        self.instrument.devicelogmanager.stopAll()
