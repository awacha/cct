from typing import Any

from PyQt5 import QtWidgets, QtGui

from .devicestatus_ui import Ui_GroupBox
from ...core2.devices.device.frontend import DeviceFrontend
from ...core2.devices.device.telemetry import TelemetryInformation


class DeviceStatus(QtWidgets.QGroupBox, Ui_GroupBox):
    device: DeviceFrontend

    def __init__(self, **kwargs):
        super().__init__(kwargs['parent'] if 'parent' in kwargs else None)
        self.device = kwargs['device']
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.statusLabel.setText('')
        self.device.connectionEnded.connect(self.onDeviceConnectionEnded)
        self.device.allVariablesReady.connect(self.onDeviceAllVariablesReady)
        self.device.variableChanged.connect(self.onDeviceVariableChanged)
        self.device.telemetry.connect(self.onDeviceTelemetry)
        self.autoQueryLabel.setAutoFillBackground(True)
        self.sendLabel.setAutoFillBackground(True)
        self.recvLabel.setAutoFillBackground(True)
        self.readyLabel.setAutoFillBackground(True)
        self.setTitle(self.device.name)
        self.setEnabled(False)

    def onDeviceVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if name in ['__status__', '__auxstatus__']:
            try:
                self.statusLabel.setText(f"{self.device['__status__']} ({self.device['__auxstatus__']})")
            except DeviceFrontend.DeviceError:
                pass

    def onDeviceConnectionEnded(self, expected: bool):
        self.close()

    def onDeviceAllVariablesReady(self):
        pass

    def onDeviceTelemetry(self, telemetryinformation: TelemetryInformation):
        self.setToolTip(str(telemetryinformation))
        self.setLabelColor(self.autoQueryLabel, not telemetryinformation.autoqueryinhibited)
        self.setLabelColor(self.sendLabel, telemetryinformation.messagessent > 0)
        self.sendLabel.setToolTip(
            f'Message rate: {telemetryinformation.messagessent / telemetryinformation.duration():.2f} messages / sec\n'
            f'Byte rate: {telemetryinformation.bytessent / telemetryinformation.duration():.2f} bytes / sec'
        )
        self.setLabelColor(self.recvLabel, telemetryinformation.messagesreceived > 0)
        self.recvLabel.setToolTip(
            f'Message rate: {telemetryinformation.messagesreceived / telemetryinformation.duration():.2f} messages / sec\n'
            f'Byte rate: {telemetryinformation.bytesreceived / telemetryinformation.duration():.2f} bytes / sec'
        )
        self.setLabelColor(self.readyLabel, not telemetryinformation.outstandingvariables)
        self.readyLabel.setToolTip('Outstanding variable queries:\n' + '\n'.join(
            [f'  {vname}' for vname in telemetryinformation.outstandingvariables]))
        self.setEnabled(True)

    @staticmethod
    def setLabelColor(label: QtWidgets.QLabel, isok: bool):
        pal = label.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor('green' if isok else 'red'))
        label.setPalette(pal)
        label.setAutoFillBackground(True)