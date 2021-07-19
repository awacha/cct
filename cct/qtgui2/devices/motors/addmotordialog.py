from PyQt5 import QtWidgets
from .addmotordialog_ui import Ui_Dialog
from ....core2.instrument.instrument import Instrument
from ....core2.devices.motor.generic.frontend import MotorController


class AddMotorDialog(QtWidgets.QDialog, Ui_Dialog):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Dialog):
        super().setupUi(Dialog)
        self.controllerComboBox.clear()
        self.controllerComboBox.addItems(sorted([m.name for m in Instrument.instance().devicemanager.motorcontrollers()]))
        self.controllerComboBox.setCurrentIndex(0)
        self.validate()
        self.controllerComboBox.currentIndexChanged.connect(self.motorControllerSelected)
        self.motorNameLineEdit.textChanged.connect(self.validate)
        self.axisSpinBox.valueChanged.connect(self.validate)
        self.leftLimitDoubleSpinBox.valueChanged.connect(self.validate)
        self.rightLimitDoubleSpinBox.valueChanged.connect(self.validate)
        self.positionDoubleSpinBox.valueChanged.connect(self.validate)

    def motorControllerSelected(self):
        controller = Instrument.instance().devicemanager[self.controllerComboBox.currentText()]
        assert isinstance(controller, MotorController)
        self.axisSpinBox.setRange(0, controller.Naxes)
        self.axisSpinBox.setValue(0)

    def validate(self):
        if (not self.motorNameLineEdit.text()) or \
            (self.motorNameLineEdit.text() in Instrument.instance().motors) or \
                (self.controllerComboBox.currentIndex() < 0) or \
                ([motor for motor in Instrument.instance().motors
                  if (motor.controllername == self.controllerComboBox.currentText())
                     and (motor.axis == self.axisSpinBox.value())]) or \
                (self.leftLimitDoubleSpinBox.value() > self.rightLimitDoubleSpinBox.value()) or \
                (self.positionDoubleSpinBox.value() < self.leftLimitDoubleSpinBox.value()) or \
                (self.positionDoubleSpinBox.value() > self.rightLimitDoubleSpinBox.value()):
            self.buttonBox.button(self.buttonBox.Ok).setEnabled(False)
        self.buttonBox.button(self.buttonBox.Ok).setEnabled(True)

    def motorName(self) -> str:
        return self.motorNameLineEdit.text()

    def axis(self) -> int:
        return self.axisSpinBox.value()

    def controllerName(self) -> str:
        return self.controllerComboBox.currentText()

    def position(self) -> float:
        return self.positionDoubleSpinBox.value()

    def leftlimit(self) -> float:
        return self.leftLimitDoubleSpinBox.value()

    def rightlimit(self) -> float:
        return self.rightLimitDoubleSpinBox.value()

