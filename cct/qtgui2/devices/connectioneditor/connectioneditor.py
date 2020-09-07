from typing import Optional

from PyQt5 import QtWidgets, QtCore

from .connectioneditor_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from .newconnectiondialog import NewConnectionDialog


class ConnectionEditor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    newconnectiondialog: Optional[NewConnectionDialog] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.addToolButton.clicked.connect(self.addDevice)
        self.connectToolButton.clicked.connect(self.connectDevice)
        self.removeToolButton.clicked.connect(self.removeDevice)
        self.disconnectToolButton.clicked.connect(self.disconnectDevice)
        self.treeView.setModel(self.instrument.devicemanager)
        for c in range(self.instrument.devicemanager.columnCount()):
            self.treeView.resizeColumnToContents(c)

    def addDevice(self):
        if self.newconnectiondialog is not None:
            return
        self.newconnectiondialog = NewConnectionDialog()
        self.newconnectiondialog.finished.connect(self.onNewConnectionDialogFinished)
        self.newconnectiondialog.show()

    def onNewConnectionDialogFinished(self, result: int):
        if result == QtWidgets.QDialog.Accepted:
            try:
                self.instrument.devicemanager.addDevice(self.newconnectiondialog.devicename(), self.newconnectiondialog.driverClassName(), self.newconnectiondialog.host(), self.newconnectiondialog.port())
            except RuntimeError:
                QtWidgets.QMessageBox.critical(self, 'Cannot add device', 'Insufficient privileges to add a new device.')
        self.newconnectiondialog.close()
        self.newconnectiondialog.deleteLater()
        self.newconnectiondialog = None

    def removeDevice(self):
        index = self.treeView.selectionModel().currentIndex()
        if not index.isValid():
            return
        devname = index.data(QtCore.Qt.UserRole)
        try:
            self.instrument.devicemanager.removeDevice(devname)
        except RuntimeError as rte:
            QtWidgets.QMessageBox.critical(self, 'Cannot remove device', str(rte))

    def connectDevice(self):
        if not self.treeView.selectionModel().currentIndex().isValid():
            return
        self.instrument.devicemanager.connectDevice(self.treeView.selectionModel().currentIndex().data(QtCore.Qt.UserRole))

    def disconnectDevice(self):
        if not self.treeView.selectionModel().currentIndex().isValid():
            return
        self.instrument.devicemanager.disconnectDevice(self.treeView.selectionModel().currentIndex().data(QtCore.Qt.UserRole))
