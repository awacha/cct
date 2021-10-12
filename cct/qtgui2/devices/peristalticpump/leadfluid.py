import logging
from typing import Any

from PyQt5 import QtWidgets

from .leadfluid_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.devices.peristalticpump.leadfluid.frontend import ControlMode, BT100S

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class LeadFluid_BT100S(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicenames = ['BT100S']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        for widget in [self.easyDispensePushButton, self.timeDispensePushButton, self.rotationSpeedDoubleSpinBox,
                       self.dispenseTimeDoubleSpinBox, self.dispenseVolumeDoubleSpinBox, self.fullSpeedPushButton,
                       self.clockwisePushButton, self.startPushButton, self.stopPushButton, self.controlModeComboBox]:
            widget.setEnabled(False)
        self.easyDispensePushButton.toggled.connect(self.onEasyDispenseToggled)
        self.timeDispensePushButton.toggled.connect(self.onTimeDispenseToggled)
        self.clockwisePushButton.toggled.connect(self.onClockwiseToggled)
        self.fullSpeedPushButton.toggled.connect(self.onFullSpeedToggled)
        self.startPushButton.clicked.connect(self.onStartClicked)
        self.stopPushButton.clicked.connect(self.onStopClicked)
        self.controlModeComboBox.addItems([cm.value.capitalize() + ' control' for cm in ControlMode])
        self.controlModeComboBox.currentIndexChanged.connect(self.onControlModeChanged)
        self.rotationSpeedDoubleSpinBox.valueChanged.connect(self.onRotationSpeedChanged)
        self.dispenseTimeDoubleSpinBox.valueChanged.connect(self.onDispenseTimeChanged)
        self.dispenseVolumeDoubleSpinBox.valueChanged.connect(self.onDispenseVolumeChanged)
        self.dispenseVolumeDoubleSpinBox.setEnabled(False)  # ToDo
        for variable in self.device().keys():
            try:
                value = self.device()[variable]
            except BT100S.DeviceError:
                continue
            self.onVariableChanged(variable, value, value)

    def device(self) -> BT100S:
        return self.instrument.devicemanager['BT100S']

    def onRotationSpeedChanged(self, value: float):
        self.rotationSpeedDoubleSpinBox.setEnabled(False)
        self.device().setRotationSpeed(value)

    def onDispenseTimeChanged(self, value: float):
        self.dispenseTimeDoubleSpinBox.setEnabled(False)
        self.device().setDispenseTime(value)

    def onDispenseVolumeChanged(self, value: float):
        return False  # ToDo
        self.dispenseVolumeDoubleSpinBox.setEnabled(False)
        self.device().setDispenseVolume(value)

    def onEasyDispenseToggled(self, active: bool):
        self.easyDispensePushButton.setEnabled(False)
        self.device().setEasyDispenseMode(active)

    def onTimeDispenseToggled(self, active: bool):
        self.timeDispensePushButton.setEnabled(False)
        self.device().setTimeDispenseMode(active)

    def onClockwiseToggled(self, active: bool):
        self.clockwisePushButton.setEnabled(False)
        self.device().setCounterClockwise(active)

    def onFullSpeedToggled(self, active: bool):
        self.fullSpeedPushButton.setEnabled(False)
        self.device().setFullSpeed(active)

    def onStartClicked(self):
        self.startPushButton.setEnabled(False)
        self.stopPushButton.setEnabled(False)
        self.device().startRotation()

    def onStopClicked(self):
        self.startPushButton.setEnabled(False)
        self.stopPushButton.setEnabled(False)
        self.device().stopRotation()

    def onControlModeChanged(self):
        self.controlModeComboBox.setEnabled(False)
        cm = ControlMode(self.controlModeComboBox.currentText().rsplit(' ', 1)[0].lower())
        self.device().setControlMode(cm)

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if name == 'steps_for_one_round':
            self.stepCountLabel.setText(f'{newvalue}')
        elif name == 'analog_speed_control':
            self.analogSpeedLabel.setText(f'{newvalue * 0.1} rpm')
        elif name == 'manufacturer':
            self.manufacturerLabel.setText(newvalue)
        elif name == 'product':
            self.productLabel.setText(newvalue)
        elif name == 'keyvalue':
            self.keyValueLabel.setText(f'{newvalue:016b}')
        elif name == 'easydispense':
            self.easyDispensePushButton.blockSignals(True)
            self.easyDispensePushButton.setChecked(newvalue)
            self.easyDispensePushButton.blockSignals(False)
            self.easyDispensePushButton.setEnabled(True)
        elif name == 'timedispense':
            self.timeDispensePushButton.blockSignals(True)
            self.timeDispensePushButton.setChecked(newvalue)
            self.timeDispensePushButton.blockSignals(False)
            self.timeDispensePushButton.setEnabled(True)
        elif name == 'rotating_speed':
            self.rotationSpeedDoubleSpinBox.blockSignals(True)
            self.rotationSpeedDoubleSpinBox.setValue(newvalue)
            self.rotationSpeedDoubleSpinBox.blockSignals(False)
            self.rotationSpeedDoubleSpinBox.setEnabled(True)
        elif name == 'direction':
            self.clockwisePushButton.blockSignals(True)
            self.clockwisePushButton.setChecked(newvalue == 'counterclockwise')
            self.clockwisePushButton.setText('Counter-clockwise' if newvalue == 'counterclockwise' else 'Clockwise')
            self.clockwisePushButton.blockSignals(False)
            self.clockwisePushButton.setEnabled(True)
        elif name == 'running':
            self.startPushButton.blockSignals(True)
            self.stopPushButton.blockSignals(True)
            self.startPushButton.setEnabled(not newvalue)
            self.stopPushButton.setEnabled(newvalue)
            self.stopPushButton.blockSignals(False)
            self.startPushButton.blockSignals(False)
        elif name == 'fullspeed':
            self.fullSpeedPushButton.blockSignals(True)
            self.fullSpeedPushButton.setChecked(newvalue)
            self.fullSpeedPushButton.setText('Full speed' if newvalue else 'Normal speed')
            self.fullSpeedPushButton.setEnabled(True)
            self.fullSpeedPushButton.blockSignals(False)
        elif name == 'control_mode':
            self.controlModeComboBox.blockSignals(True)
            self.controlModeComboBox.setCurrentIndex(
                self.controlModeComboBox.findText(newvalue.capitalize() + ' control'))
            self.controlModeComboBox.setEnabled(True)
            self.controlModeComboBox.blockSignals(False)
        elif name == 'easy_dispense_volume':
            self.dispenseVolumeDoubleSpinBox.blockSignals(True)
            self.dispenseVolumeDoubleSpinBox.setValue(newvalue)
            self.dispenseVolumeDoubleSpinBox.blockSignals(False)
            self.dispenseVolumeDoubleSpinBox.setEnabled(False)  # ToDo
        elif name == 'dispense_time':
            self.dispenseTimeDoubleSpinBox.blockSignals(True)
            self.dispenseTimeDoubleSpinBox.setValue(newvalue)
            self.dispenseTimeDoubleSpinBox.setEnabled(True)
            self.dispenseTimeDoubleSpinBox.blockSignals(False)
        elif name in ['rotating_speed_timer', '__status__', '__auxstatus__', 'modbusaddress', 'littleendian']:
            pass
        else:
            logger.warning(f'Unknown variable {name}, new value {newvalue}')
