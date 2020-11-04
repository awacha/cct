from typing import Any, Final, Dict, Tuple

from PyQt5 import QtWidgets
from ...utils.window import WindowRequiresDevices
from .pilatus_ui import Ui_Form
from ....core2.devices.detector.pilatus.frontend import PilatusDetector, PilatusGain, PilatusBackend


class PilatusDetectorUI(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicenames = ['pilatus']
    thresholdsettings: Final[Dict[str, Tuple[float, PilatusGain]]] = {
        'Cu': (4024, PilatusGain.High),
        'Ag': (11082, PilatusGain.Low),
        'Cr': (3814, PilatusGain.High),
        'Fe': (3814, PilatusGain.High),  # yes, same as Cr
        'Mo': (8740, PilatusGain.Low),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.devicemanager.detector())
        self.trimPushButton.clicked.connect(self.onTrimButtonClicked)
        self.gainComboBox.addItems([p.value for p in PilatusGain])
        self.gainComboBox.setCurrentIndex(0)
        self.gainComboBox.currentIndexChanged.connect(self.updateThresholdLimits)
        self.gainComboBox.setCurrentIndex(self.gainComboBox.findText(self.instrument.devicemanager.detector()['gain']))
        self.thresholdSpinBox.setValue(self.instrument.devicemanager.detector()['threshold'])
        for quicktrimtoolbutton in [self.setAgToolButton, self.setCrToolButton, self.setCuToolButton, self.setFeToolButton, self.setMoToolButton]:
            quicktrimtoolbutton.clicked.connect(self.onQuickTrim)

    def onQuickTrim(self):
        if self.sender() is self.setAgToolButton:
            threshold, gain = self.thresholdsettings['Ag']
        elif self.sender() is self.setCrToolButton:
            threshold, gain = self.thresholdsettings['Cr']
        elif self.sender() is self.setCuToolButton:
            threshold, gain = self.thresholdsettings['Cu']
        elif self.sender() is self.setFeToolButton:
            threshold, gain = self.thresholdsettings['Fe']
        elif self.sender() is self.setMoToolButton:
            threshold, gain = self.thresholdsettings['Mo']
        else:
            assert False
        self.gainComboBox.setCurrentIndex(self.gainComboBox.findText(gain.value))
        self.thresholdSpinBox.setValue(threshold)
        self.trimPushButton.click()

    def updateThresholdLimits(self):
        if self.gainComboBox.currentIndex() < 0:
            return
        gain = PilatusGain(self.gainComboBox.currentText())
        detector = self.instrument.devicemanager.detector()
        assert isinstance(detector, PilatusDetector)
        self.thresholdSpinBox.setRange(*detector.thresholdLimits(gain))

    def onTrimButtonClicked(self):
        detector = self.instrument.devicemanager.detector()
        assert isinstance(detector, PilatusDetector)
        detector.trim(self.thresholdSpinBox.value(), PilatusGain(self.gainComboBox.currentText()))

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if self.sender() is self.instrument.devicemanager.detector():
            if name == '__status__':
                self.trimPushButton.setEnabled(newvalue == PilatusBackend.Status.Idle)
            elif name == 'gain':
                self.gainComboBox.setCurrentIndex(self.gainComboBox.findText(self.sender()['gain']))
                self.thresholdSpinBox.setValue(self.sender()['threshold'])
            elif name == 'threshold':
                self.thresholdSpinBox.setValue(self.sender()['threshold'])

