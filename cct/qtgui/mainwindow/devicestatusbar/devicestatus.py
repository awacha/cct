import typing

from PyQt5 import QtWidgets, QtGui

from .devicestatus_ui import Ui_Form
from ....core.devices.device import Device
from ....core.services.telemetry import TelemetryInfo


class DeviceStatus(QtWidgets.QWidget, Ui_Form):
    def __init__(self, parent, device: Device):
        super().__init__(parent)
        self.device = device
        self._connections = []
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.deviceNameLabel.setText(self.device.name)
        self._connections = [self.device.connect('telemetry', self.onDeviceTelemetry),
                             self.device.connect('disconnect', self.onDeviceDisconnect),
                             self.device.connect('variable-change', self.onDeviceVariableChange),
                             self.device.connect('ready', self.onDeviceReady)]
        self.checkIfReady(self.device)
        self.onDeviceVariableChange(self.device, '_status', self.device.get_variable('_status'))

    def onDeviceReady(self, device: Device):
        self.checkIfReady(device)

    def onDeviceVariableChange(self, device: Device, var: str, value: typing.Any):
        status = device.get_variable('_status')
        if var == '_status':
            status = value
            auxstatus = device.get_variable('_auxstatus')
        elif var == '_auxstatus':
            status = device.get_variable('_status')
            auxstatus = value
        else:
            return False
        self.deviceStatusLabel.setText('{} ({})'.format(status, auxstatus))
        self.checkIfDeviceIsConnected(device)
        self.checkIfReady(device)
        self.checkIfBusy(device, status=status)
        return False

    def checkIfDeviceIsConnected(self, device: Device):
        if device.get_connected():
            color = QtGui.QColor('lightgreen')
            tooltip = 'Connected to {}'.format(':'.join([str(x) for x in device.deviceconnectionparameters]))
        else:
            color = QtGui.QColor('red')
            tooltip = 'Disconnected'
        self.setLabelBackgroundColor(self.connectedLabel, color)
        self.connectedLabel.setToolTip(tooltip)

    def checkIfReady(self, device: Device):
        if device.is_ready():
            color = QtGui.QColor('lightgreen')
            tooltip = 'Device is ready'
        else:
            color = QtGui.QColor('red')
            tooltip = 'Device is not ready'
        self.setLabelBackgroundColor(self.readyLabel, color)
        self.readyLabel.setToolTip(tooltip)

    def checkIfBusy(self, device: Device, status=None):
        if device.is_busy(status):
            color = QtGui.QColor('yellow')
            tooltip = 'Device is busy'
            text = 'BU'
        else:
            color = QtGui.QColor('lightgreen')
            tooltip = 'Device is idle'
            text = 'ID'
        self.setLabelBackgroundColor(self.busyLabel, color)
        self.busyLabel.setToolTip(tooltip)
        self.busyLabel.setText(text)

    def onDeviceDisconnect(self, device: Device, unexpected: bool):
        self.checkIfDeviceIsConnected(device)
        self.checkIfReady(device)

    def cleanup(self):
        for c in self._connections:
            self.device.disconnect(c)
        self._connections = []

    def onDeviceTelemetry(self, device: Device, telemetry: TelemetryInfo):
        if telemetry.last_recv > 5:
            color = QtGui.QColor('red')
            tooltip = 'Device is not responding. Last message received {:.3f} seconds ago'.format(telemetry.last_recv)
        else:
            color = QtGui.QColor('lightgreen')
            tooltip = 'Last message received {:.3f} seconds ago'.format(telemetry.last_recv)
        self.setLabelBackgroundColor(self.lastRecvLabel, color)
        self.lastRecvLabel.setToolTip(tooltip)

        if telemetry.last_send > 5:
            color = QtGui.QColor('red')
            tooltip = 'Not sending to device. Last message sent {:.3f} seconds ago'.format(telemetry.last_send)
        else:
            color = QtGui.QColor('lightgreen')
            tooltip = 'Last message sent {:.3f} seconds ago'.format(telemetry.last_send)
        self.setLabelBackgroundColor(self.lastSendLabel, color)
        self.lastSendLabel.setToolTip(tooltip)

        if telemetry.watchdog_active:
            if telemetry.watchdog > telemetry.watchdog_timeout:
                color = QtGui.QColor('red')
                tooltip = 'Communication watchdog error (wd value: {:.2f} sec)'.format(telemetry.watchdog)
            elif telemetry.watchdog > telemetry.watchdog_timeout * 0.5:
                color = QtGui.QColor('yellow')
                tooltip = 'Communication watchdog warning (wd value: {:.2f} sec)'.format(telemetry.watchdog)
            else:
                color = QtGui.QColor('lightgreen')
                tooltip = 'Communication watchdog OK (wd value: {:.2f} sec)'.format(telemetry.watchdog)
            self.setLabelBackgroundColor(self.watchDogLabel, color)
            self.watchDogLabel.setToolTip(tooltip)
            self.watchDogLabel.setEnabled(True)
        else:
            self.watchDogLabel.setEnabled(False)
            self.setLabelBackgroundColor(self.watchDogLabel, QtGui.QColor('gray'))

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.cleanup()
        event.accept()

    def setLabelBackgroundColor(self, label: QtWidgets.QLabel, color: QtGui.QColor):
        pal = label.palette()
        pal.setColor(QtGui.QPalette.Window, color)
        label.setPalette(pal)
        label.setAutoFillBackground(True)
