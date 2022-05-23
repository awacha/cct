from typing import Optional

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSlot as Slot

from .connectioneditor_ui import Ui_Form
from ....core2.devices.device.telemetry import TelemetryInformation
from ...utils.window import WindowRequiresDevices
from .newconnectiondialog import NewConnectionDialog
from .telemetrymodel import TelemetryModel


class ConnectionEditor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    newconnectiondialog: Optional[NewConnectionDialog] = None
    connect_all_devices = True

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
        self.telemetryTreeView.setModel(TelemetryModel())
        self.deviceComboBox.currentIndexChanged.connect(self.onDeviceChanged)
        self.updateDeviceComboBox()
        if self.deviceComboBox.currentIndex() >= 0:
            self.variablesTreeView.setModel(self.instrument.devicemanager[self.deviceComboBox.currentText()])

    @Slot()
    def addDevice(self):
        if self.newconnectiondialog is not None:
            return
        self.newconnectiondialog = NewConnectionDialog()
        self.newconnectiondialog.finished.connect(self.onNewConnectionDialogFinished)
        self.newconnectiondialog.show()

    @Slot(int)
    def onNewConnectionDialogFinished(self, result: int):
        if result == QtWidgets.QDialog.Accepted:
            try:
                self.instrument.devicemanager.addDevice(self.newconnectiondialog.devicename(), self.newconnectiondialog.driverClassName(), self.newconnectiondialog.host(), self.newconnectiondialog.port())
            except RuntimeError:
                QtWidgets.QMessageBox.critical(self, 'Cannot add device', 'Insufficient privileges to add a new device.')
        self.newconnectiondialog.close()
        self.newconnectiondialog.deleteLater()
        self.newconnectiondialog = None

    @Slot()
    def removeDevice(self):
        index = self.treeView.selectionModel().currentIndex()
        if not index.isValid():
            return
        devname = index.data(QtCore.Qt.UserRole)
        try:
            self.instrument.devicemanager.removeDevice(devname)
        except RuntimeError as rte:
            QtWidgets.QMessageBox.critical(self, 'Cannot remove device', str(rte))

    @Slot()
    def connectDevice(self):
        if not self.treeView.selectionModel().currentIndex().isValid():
            return
        self.instrument.devicemanager.connectDevice(
            self.treeView.selectionModel().currentIndex().data(QtCore.Qt.UserRole))

    @Slot()
    def disconnectDevice(self):
        if not self.treeView.selectionModel().currentIndex().isValid():
            return
        self.instrument.devicemanager.disconnectDevice(
            self.treeView.selectionModel().currentIndex().data(QtCore.Qt.UserRole))

    @Slot(str)
    def onDeviceAdded(self, devicename: str):
        self.updateDeviceComboBox()

    @Slot(str, bool)
    def onDeviceRemoved(self, devicename: str, expected: bool):
        self.updateDeviceComboBox()

    def updateDeviceComboBox(self):
        if not hasattr(self, 'deviceComboBox'):
            # can happen when setupUi() has not yet been run, but the WindowRequiresDevices __init__ is running.
            return
        currentdevice = self.deviceComboBox.currentText() if self.deviceComboBox.currentIndex() >= 0 else None
        self.deviceComboBox.blockSignals(True)
        try:
            self.deviceComboBox.clear()
            self.deviceComboBox.addItems(sorted([d.name for d in self.instrument.devicemanager]))
            if currentdevice is not None:
                self.deviceComboBox.setCurrentIndex(self.deviceComboBox.findText(currentdevice))
            # otherwise currentIndex will be -1
        finally:
            self.deviceComboBox.blockSignals(False)
        if (currentdevice is None) or (self.deviceComboBox.currentIndex()<0):
            self.deviceComboBox.setCurrentIndex(0)

    @Slot(object)
    def onDeviceTelemetry(self, telemetry: TelemetryInformation):
        if self.sender().name == self.deviceComboBox.currentText():
            self.telemetryTreeView.model().setTelemetry(telemetry)

    @Slot()
    def onDeviceChanged(self):
        self.telemetryTreeView.model().setTelemetry(None)
        if self.deviceComboBox.currentIndex() >= 0:
            self.variablesTreeView.setModel(self.instrument.devicemanager[self.deviceComboBox.currentText()])