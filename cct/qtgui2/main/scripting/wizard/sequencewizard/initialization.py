from PyQt5 import QtWidgets

from .initialization_ui import Ui_WizardPage
from ......core2.devices.detector import PilatusGain, PilatusDetector


class InitPage(QtWidgets.QWizardPage, Ui_WizardPage):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, WizardPage):
        super().setupUi(WizardPage)
        self.gainComboBox.addItems([p.value for p in PilatusGain])
        self.gainComboBox.currentIndexChanged.connect(self.onGainChanged)
        self.gainComboBox.setCurrentIndex(self.gainComboBox.findText(PilatusGain.High.value))
        self.thresholdSpinBox.setValue(4024)
        self.xRayPowerComboBox.addItems(['off', 'standby', 'full'])
        self.xRayPowerComboBox.setCurrentIndex(2)
        self.registerField('closeShutterBefore', self.closeShutterCheckBox, 'checked',
                           self.closeShutterCheckBox.toggled)
        self.registerField('beamstopIn', self.beamstopInCheckBox, 'checked', self.beamstopInCheckBox.toggled)
        self.registerField('initializeXraySourceTo', self.xRayPowerComboBox, 'currentText',
                           self.xRayPowerComboBox.currentTextChanged)
        self.registerField('initializeXraySource', self.xRayPowerCheckBox, 'checked', self.xRayPowerCheckBox.toggled)
        self.registerField('trimDetector', self.trimCheckBox, 'checked', self.trimCheckBox.toggled)
        self.registerField('gain', self.gainComboBox, 'currentText', self.gainComboBox.currentTextChanged)
        self.registerField('threshold', self.thresholdSpinBox, 'value', self.thresholdSpinBox.valueChanged)
        self.registerField('setSampleTemperature', self.temperatureCheckBox, 'checked',
                           self.temperatureCheckBox.toggled)
        self.registerField('sampleTemperature', self.temperatureDoubleSpinBox, 'value',
                           self.temperatureDoubleSpinBox.valueChanged)
        self.registerField('openShutterBefore', self.openShutterCheckBox, 'checked', self.openShutterCheckBox.toggled)

    def onGainChanged(self, index: int):
        gain = PilatusGain(self.gainComboBox.currentText())
        self.thresholdSpinBox.setRange(*PilatusDetector.thresholdLimits(gain))
