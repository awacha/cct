import logging
from typing import Any, Optional

from PyQt5 import QtWidgets, QtGui

from .devicestatus_ui import Ui_GroupBox
from ...core2.devices.device.frontend import DeviceFrontend
from ...core2.devices.device.telemetry import TelemetryInformation
from ...core2.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DeviceStatus(QtWidgets.QGroupBox, Ui_GroupBox):
    devicename: str

    def __init__(self, **kwargs):
        super().__init__(kwargs['parent'] if 'parent' in kwargs else None)
        self.devicename = kwargs['devicename']
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.statusLabel.setText('')
        self.autoQueryLabel.setAutoFillBackground(True)
        self.sendLabel.setAutoFillBackground(True)
        self.recvLabel.setAutoFillBackground(True)
        self.readyLabel.setAutoFillBackground(True)
        self.reconnectToolButton.clicked.connect(self.reconnect)
        self.setTitle(self.device.name)
        if self.devicename in Instrument.instance().devicemanager:
            self._connectDevice()
        else:
            self.onDeviceDisconnected()

    def reconnect(self):
        if Instrument.instance().devicemanager[self.devicename].isOffline():
            Instrument.instance().devicemanager.connectDevice(self.devicename)
        else:
            Instrument.instance().devicemanager.disconnectDevice(self.devicename)
        self.reconnectToolButton.setEnabled(False)

    def onDeviceAllVariablesReady(self):
        self.reconnectToolButton.setText('D')
        self.reconnectToolButton.setIcon(QtGui.QIcon.fromTheme('network-disconnect'))
        self.reconnectToolButton.setToolTip('Disconnect from the device')
        self.reconnectToolButton.setEnabled(True)

    def onDeviceDisconnected(self):
        self.reconnectToolButton.setText('C')
        self.reconnectToolButton.setIcon(QtGui.QIcon.fromTheme('network-connect'))
        self.reconnectToolButton.setToolTip('Connect to the device')
        self.reconnectToolButton.setEnabled(True)
        self.setLabelColor(self.recvLabel, None)
        self.setLabelColor(self.sendLabel, None)
        self.setLabelColor(self.readyLabel, None)
        self.setLabelColor(self.autoQueryLabel, None)
        self.statusLabel.setText('(disconnected)')

    def _connectDevice(self):
        self.device.allVariablesReady.connect(self.onDeviceAllVariablesReady)
        self.device.connectionLost.connect(self.onDeviceDisconnected)
        self.device.variableChanged.connect(self.onDeviceVariableChanged)
        self.device.telemetry.connect(self.onDeviceTelemetry)

    def onDeviceVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if name in ['__status__', '__auxstatus__']:
            try:
                self.statusLabel.setText(f"{self.device['__status__']} ({self.device['__auxstatus__']})")
            except DeviceFrontend.DeviceError:
                pass

    def onDeviceTelemetry(self, telemetryinformation: TelemetryInformation):
        self.setToolTip(str(telemetryinformation))
        self.setLabelColor(self.autoQueryLabel, not telemetryinformation.autoqueryinhibited)
        self.setLabelColor(self.sendLabel, telemetryinformation.messagessent > 0)
        self.sendLabel.setToolTip(
            f'Message rate: {telemetryinformation.messagessent / telemetryinformation.duration:.2f} messages / sec\n'
            f'Byte rate: {telemetryinformation.bytessent / telemetryinformation.duration:.2f} bytes / sec'
        )
        self.setLabelColor(self.recvLabel, telemetryinformation.messagesreceived > 0)
        self.recvLabel.setToolTip(
            f'Message rate: {telemetryinformation.messagesreceived / telemetryinformation.duration:.2f} messages / sec\n'
            f'Byte rate: {telemetryinformation.bytesreceived / telemetryinformation.duration:.2f} bytes / sec'
        )
        self.setLabelColor(self.readyLabel, not telemetryinformation.outstandingvariables)
        self.readyLabel.setToolTip('Outstanding variable queries:\n' + '\n'.join(
            [f'  {vname}' for vname in telemetryinformation.outstandingvariables]))

    @staticmethod
    def setLabelColor(label: QtWidgets.QLabel, isok: Optional[bool]):
        pal = label.palette()
        pal.setColor(
            QtGui.QPalette.Window,
            QtGui.QColor(
                ('lightgreen' if isok else 'red') if isok is not None else 'gray'))
        label.setPalette(pal)
        label.setAutoFillBackground(True)

    @property
    def device(self) -> DeviceFrontend:
        return Instrument.instance().devicemanager[self.devicename]
