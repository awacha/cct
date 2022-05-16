from typing import Any
import logging

from PyQt5 import QtWidgets
from ...utils.window import WindowRequiresDevices
from .schottKL2500LED_ui import Ui_Form
from ....core2.devices.illumination.schott.frontend import KL2500LED

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SchottKL2500LEDUI(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicenames = ['KL2500LED']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.brightnessHorizontalSlider.valueChanged.connect(self.onSliderChanged)
        self.brightnessHorizontalSlider.setMinimum(0)
        self.brightnessHorizontalSlider.setMaximum(self.device().maximumBrightness)
        self.shutterPushButton.toggled.connect(self.onShutterToggled)
        self.frontPanelLockoutPushButton.toggled.connect(self.onFrontPanelLockoutToggled)
        for variable in self.device().keys():
            self.onVariableChanged(variable, self.device()[variable], self.device()[variable])

    def device(self) -> KL2500LED:
        dev = [d for d in self.instrument.devicemanager if d.devicename == 'KL2500LED'][0]
        assert isinstance(dev, KL2500LED)
        return dev

    def onSliderChanged(self, value: int):
        self.device().setBrightness(value)

    def onShutterToggled(self, active: bool):
        if active:
            self.device().closeShutter()
        else:
            self.device().openShutter()

    def onFrontPanelLockoutToggled(self, active: bool):
        self.device().frontPanelLockout(active)

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if name == 'brightness':
            self.brightnessLabel.setText(f'{newvalue}')
            self.brightnessHorizontalSlider.blockSignals(True)
            self.brightnessHorizontalSlider.setValue(newvalue)
            self.brightnessHorizontalSlider.blockSignals(False)
        elif name == 'hardwareversion':
            self.hardwareLabel.setText(newvalue)
        elif name == 'frontpanellockout':
            self.frontPanelLockoutPushButton.blockSignals(True)
            self.frontPanelLockoutPushButton.setChecked(newvalue)
            self.frontPanelLockoutPushButton.blockSignals(False)
        elif name == 'protocolversion':
            self.protocolVersionLabel.setText(f'{newvalue:.2f}')
        elif name == 'shutter':
            self.shutterPushButton.blockSignals(True)
            self.shutterPushButton.setChecked(newvalue)
            self.shutterPushButton.blockSignals(False)
        elif name == 'temperature':
            self.temperatureLcdNumber.display(newvalue)
