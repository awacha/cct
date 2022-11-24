from PySide6 import QtWidgets
from PySide6.QtCore import Slot
from .addmotordialog_ui import Ui_Dialog
from ....core2.instrument.instrument import Instrument
from ....core2.devices.motor.generic.frontend import MotorController
from ....core2.instrument.components.motors.motors import MotorRole, MotorDirection


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
        self.motorRoleComboBox.addItems([role.name for role in MotorRole])
        self.motorRoleComboBox.setCurrentIndex(0)
        self.motorDirectionComboBox.addItems([direction.name for direction in MotorDirection])
        self.motorDirectionComboBox.setCurrentIndex(0)

    @Slot()
    def motorControllerSelected(self):
        controller = Instrument.instance().devicemanager[self.controllerComboBox.currentText()]
        assert isinstance(controller, MotorController)
        self.axisSpinBox.setRange(0, controller.Naxes)
        self.axisSpinBox.setValue(0)

    @Slot()
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

    def motorrole(self) -> MotorRole:
        return MotorRole[self.motorRoleComboBox.currentText()]

    def motordirection(self) -> MotorDirection:
        return MotorDirection[self.motorDirectionComboBox.currentText()]