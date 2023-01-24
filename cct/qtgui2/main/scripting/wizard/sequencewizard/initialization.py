from PySide6 import QtWidgets
from PySide6.QtCore import Slot

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
        self.registerField('closeShutterBefore', self.closeShutterCheckBox, 'checked', 'toggled')
        self.registerField('beamstopIn', self.beamstopInCheckBox, 'checked', 'toggled')
        self.registerField('initializeXraySourceTo', self.xRayPowerComboBox, 'currentText', 'currentTextChanged')
        self.registerField('initializeXraySource', self.xRayPowerCheckBox, 'checked', 'toggled')
        self.registerField('trimDetector', self.trimCheckBox, 'checked', 'toggled')
        self.registerField('gain', self.gainComboBox, 'currentText', 'currentTextChanged')
        self.registerField('threshold', self.thresholdSpinBox, 'value', 'valueChanged')
        self.registerField('setSampleTemperature', self.temperatureCheckBox, 'checked', 'toggled')
        self.registerField('sampleTemperature', self.temperatureDoubleSpinBox, 'value', 'valueChanged')
        self.registerField('openShutterBefore', self.openShutterCheckBox, 'checked', 'toggled')

    @Slot(int)
    def onGainChanged(self, index: int):
        gain = PilatusGain(self.gainComboBox.currentText())
        self.thresholdSpinBox.setRange(*PilatusDetector.thresholdLimits(gain))
