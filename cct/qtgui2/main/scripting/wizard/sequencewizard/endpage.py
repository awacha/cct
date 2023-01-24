from PySide6 import QtWidgets
from .endpage_ui import Ui_WizardPage


class EndPage(QtWidgets.QWizardPage, Ui_WizardPage):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, WizardPage):
        super().setupUi(WizardPage)
        self.xRaySourcePowerModeComboBox.addItems(['off', 'standby', 'full'])
        self.registerField('iterationCount', self.iterationCountSpinBox, b'value', b'valueChanged')
        self.registerField('userBreakFlag', self.addUserBreakFlagCheckBox, b'checked', b'toggled')
        self.registerField('closeShutterAfter', self.closeShutterCheckBox, b'checked', b'toggled')
        self.registerField('setXraySourcePowerAfter', self.setXraySourcePowerModeCheckBox, b'checked', b'toggled')
        self.registerField('setXraySourcePowerAfterTo', self.xRaySourcePowerModeComboBox, b'currentText', b'currentTextChanged')


