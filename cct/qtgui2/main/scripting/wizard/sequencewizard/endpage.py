from PyQt5 import QtWidgets
from .endpage_ui import Ui_WizardPage


class EndPage(QtWidgets.QWizardPage, Ui_WizardPage):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, WizardPage):
        super().setupUi(WizardPage)
        self.xRaySourcePowerModeComboBox.addItems(['off', 'standby', 'full'])
        self.registerField('iterationCount', self.iterationCountSpinBox, 'value', self.iterationCountSpinBox.valueChanged)
        self.registerField('userBreakFlag', self.addUserBreakFlagCheckBox, 'checked', self.addUserBreakFlagCheckBox.toggled)
        self.registerField('closeShutterAfter', self.closeShutterCheckBox, 'checked', self.closeShutterCheckBox.toggled)
        self.registerField('setXraySourcePowerAfter', self.setXraySourcePowerModeCheckBox, 'checked', self.setXraySourcePowerModeCheckBox.toggled)
        self.registerField('setXraySourcePowerAfterTo', self.xRaySourcePowerModeComboBox, 'currentText', self.xRaySourcePowerModeComboBox.currentTextChanged)


