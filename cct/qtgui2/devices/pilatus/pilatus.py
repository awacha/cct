from typing import Any

from PyQt5 import QtWidgets
from ...utils.window import WindowRequiresDevices
from .pilatus_ui import Ui_Form
from ....core2.devices.detector.pilatus.frontend import PilatusDetector, PilatusGain, PilatusBackend


class PilatusDetectorUI(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicenames = ['pilatus']

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

