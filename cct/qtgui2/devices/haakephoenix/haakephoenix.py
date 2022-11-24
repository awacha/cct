from typing import Any, Optional
import datetime

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Slot
from .haakephoenix_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.devices.thermostat.haakephoenix.backend import HaakePhoenixBackend
from ....core2.devices.thermostat.haakephoenix.frontend import HaakePhoenix
from ....core2.devices.device.frontend import DeviceFrontend


class HaakePhoenixDevice(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicenames = ['HaakePhoenix']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        for var in self.device().keys():
            self.onVariableChanged(var, self.device()[var], None)
        self.lowLimitDoubleSpinBox.valueChanged.connect(self.setPointDoubleSpinBox.setMinimum)
        self.highLimitDoubleSpinBox.valueChanged.connect(self.setPointDoubleSpinBox.setMaximum)
        self.updateHighLimitPushButton.clicked.connect(self.updateHighLimit)
        self.updateLowLimitPushButton.clicked.connect(self.updateLowLimit)
        self.updateSetPointPushButton.clicked.connect(self.updateSetpoint)
        self.startStopPushButton.clicked.connect(self.startStop)
        self.updateRTCPushButton.clicked.connect(self.setRTC)
        self.resize(self.minimumSizeHint())

    def setErrorFlag(self, widget: QtWidgets.QLabel, iserror: bool, label: Optional[str] = None):
        palette = widget.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor('red' if iserror else 'lightgreen'))
        widget.setPalette(palette)
        widget.setAutoFillBackground(True)
        if label is not None:
            widget.setText(label)
        try:
            self.lowLimitDoubleSpinBox.setValue(self.device()['lowlimit'])
        except DeviceFrontend.DeviceError:
            pass
        try:
            self.highLimitDoubleSpinBox.setValue(self.device()['highlimit'])
        except DeviceFrontend.DeviceError:
            pass
        try:
            self.setPointDoubleSpinBox.setValue(self.device()['setpoint'])
        except DeviceFrontend.DeviceError:
            pass

    @Slot()
    def updateHighLimit(self):
        self.device().setHighLimit(self.highLimitDoubleSpinBox.value())

    @Slot()
    def updateLowLimit(self):
        self.device().setLowLimit(self.lowLimitDoubleSpinBox.value())

    @Slot()
    def updateSetpoint(self):
        self.device().setSetpoint(self.setPointDoubleSpinBox.value())

    @Slot()
    def startStop(self):
        if self.startStopPushButton.text() == 'Start':
            self.device().startCirculator()
        else:
            self.device().stopCirculator()

    @Slot()
    def setRTC(self):
        self.device().setTime(datetime.datetime.now().time())
        self.device().setDate(datetime.datetime.now().date())

    @Slot(str, object, object)
    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if name == 'firmwareversion':
            self.firmwareVersionLabel.setText(newvalue)
        elif name == 'external_pt100_error':
            self.setErrorFlag(self.externalPt100ErrorFlag, newvalue)
        elif name == 'internal_pt100_error':
            self.setErrorFlag(self.internalPt100ErrorFlag, newvalue)
        elif name == 'cooling_error':
            self.setErrorFlag(self.coolingSystemErrorFlag, newvalue)
        elif name == 'liquid_level_low_error':
            self.setErrorFlag(self.liquidLevelErrorFlag, newvalue)
        elif name == 'external_alarm_error':
            self.setErrorFlag(self.externalAlarmErrorFlag, newvalue)
        elif name == 'pump_overload_error':
            self.setErrorFlag(self.pumpErrorFlag, newvalue)
        elif name == 'liquid_level_alarm_error':
            self.setErrorFlag(self.liquidLevelAlarmErrorFlag, newvalue)
        elif name == 'overtemperature_error':
            self.setErrorFlag(self.overtemperatureErrorFlag, newvalue)
        elif name == 'main_relay_missing_error':
            self.setErrorFlag(self.mainRelayErrorFlag, newvalue)
        elif name == 'control_external':
            self.setErrorFlag(self.externalControlStatusFlag, False, 'External control' if newvalue else 'Internal control')
        elif name == 'temperature_control':
            self.setErrorFlag(self.temperatureControlFlag, not newvalue)
        elif name == 'fuzzycontrol':
            self.setErrorFlag(self.fuzzyControlStatusFlag, newvalue)
        elif name == 'fuzzystatus':
            self.setErrorFlag(self.fuzzyStatusStatusFlag, newvalue)
        elif name == 'temperature':
            self.temperatureLcdNumber.display(newvalue)
        elif name == 'setpoint':
            self.setpointLcdNumber.display(newvalue)
        elif name == 'highlimit':
            self.highLimitLcdNumber.display(newvalue)
        elif name == 'lowlimit':
            self.lowLimitLcdNumber.display(newvalue)
        elif name == 'diffcontrol_on':
            self.setErrorFlag(self.diffControlStatusFlag, not newvalue)
        elif name == 'autostart':
            self.setErrorFlag(self.autostartStatusFlag, not newvalue)
        elif name == 'fuzzyid':
            pass
        elif name == 'beep':
            self.setErrorFlag(self.beepStatusFlag, not newvalue)
        elif name == 'time':
            assert isinstance(newvalue, datetime.time)
            self.rtcTimeEdit.setTime(QtCore.QTime(newvalue.hour, newvalue.minute, newvalue.second))
        elif name == 'date':
            assert isinstance(newvalue, datetime.date)
            self.rtcDateEdit.setDate(QtCore.QDate(newvalue.year, newvalue.month, newvalue.day))
        elif name == 'watchdog_on':
            pass
        elif name == 'watchdog_setpoint':
            pass
        elif name =='cooling_on':
            self.setErrorFlag(self.coolingOnStatusFlag, not newvalue, 'Cooling on' if newvalue else 'Cooling off')
        elif name == 'pump_power':
            self.pumpSpeedLcdNumber.display(newvalue)
        elif name == '__status__':
            self.startStopPushButton.setText('Stop' if newvalue == HaakePhoenixBackend.Status.Running else 'Start')
            self.startStopPushButton.setIcon(
                QtGui.QIcon(QtGui.QPixmap(
                    ':/icons/stop.svg' if newvalue == HaakePhoenixBackend.Status.Running else ':/icons/start.svg')))
            self.statusLabel.setText(newvalue)

    def device(self) -> HaakePhoenix:
        assert isinstance(self.instrument.devicemanager['haakephoenix'], HaakePhoenix)
        return self.instrument.devicemanager['haakephoenix']