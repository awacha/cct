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
        self.registerField('closeShutterBefore', self.closeShutterCheckBox, b'checked', b'toggled')
        self.registerField('beamstopIn', self.beamstopInCheckBox, b'checked', b'toggled')
        self.registerField('initializeXraySourceTo', self.xRayPowerComboBox, b'currentText', b'currentTextChanged')
        self.registerField('initializeXraySource', self.xRayPowerCheckBox, b'checked', b'toggled')
        self.registerField('trimDetector', self.trimCheckBox, b'checked', b'toggled')
        self.registerField('gain', self.gainComboBox, b'currentText', b'currentTextChanged')
        self.registerField('threshold', self.thresholdSpinBox, b'value', b'valueChanged')
        self.registerField('setSampleTemperature', self.temperatureCheckBox, b'checked', b'toggled')
        self.registerField('sampleTemperature', self.temperatureDoubleSpinBox, b'value', b'valueChanged')
        self.registerField('openShutterBefore', self.openShutterCheckBox, b'checked', b'toggled')

    @Slot(int)
    def onGainChanged(self, index: int):
        gain = PilatusGain(self.gainComboBox.currentText())
        self.thresholdSpinBox.setRange(*PilatusDetector.thresholdLimits(gain))
