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
        self.xRayPowerComboBox.addItems(['off', 'standby', 'full'])
        self.xRayPowerComboBox.setCurrentIndex(2)
        self.registerField('openShutterBefore', self.openShutterCheckBox, 'checked',
                           self.openShutterCheckBox.toggled)
        self.registerField('beamstopOutBefore', self.beamstopOutCheckBox, 'checked', self.beamstopOutCheckBox.toggled)
        self.registerField('initializeXraySourceTo', self.xRayPowerComboBox, 'currentText',
                           self.xRayPowerComboBox.currentTextChanged)
        self.registerField('initializeXraySource', self.xRayPowerCheckBox, 'checked', self.xRayPowerCheckBox.toggled)
        self.registerField('openShutterBefore', self.openShutterCheckBox, 'checked', self.openShutterCheckBox.toggled)
