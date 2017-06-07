from PyQt5 import QtWidgets, QtGui

from .movemotor_ui import Ui_Form
from ....core.mixins import ToolWindow
from .....core.devices import Motor
from .....core.instrument.privileges import PRIV_MOVEMOTORS


class MoveMotor(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_privilege = PRIV_MOVEMOTORS

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        self.motorname = kwargs.pop('motorname')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo, required_devices=['Motor_' + self.motorname])
        self._start_requested = False
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.motorComboBox.addItems(sorted(self.credo.motors.keys()))
        self.motorComboBox.currentTextChanged.connect(self.onMotorSelected)
        self.movePushButton.clicked.connect(self.onMove)
        self.motorComboBox.setCurrentIndex(self.motorComboBox.findText(self.motorname))
        self.relativeCheckBox.toggled.connect(self.onRelativeChanged)

    def onRelativeChanged(self):
        self.onMotorPositionChange(self.motor(), self.motor().where())

    def setIdle(self):
        super().setIdle()
        self.movePushButton.setText('Move')
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/motor.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.movePushButton.setIcon(icon)
        self.targetDoubleSpinBox.setEnabled(True)
        self.motorComboBox.setEnabled(True)
        self.relativeCheckBox.setEnabled(True)
        self.movePushButton.setEnabled(True)
        self._start_requested = False

    def setBusy(self):
        self.movePushButton.setText('Stop')
        self.movePushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
        self.targetDoubleSpinBox.setEnabled(False)
        self.motorComboBox.setEnabled(False)
        self.relativeCheckBox.setEnabled(False)
        self.movePushButton.setEnabled(True)
        super().setBusy()

    def motor(self) -> Motor:
        return self.credo.motors[self.motorComboBox.currentText()]

    def onMove(self):
        if self.movePushButton.text() == 'Move':
            self.movePushButton.setEnabled(False)
            self._start_requested = True
            if self.relativeCheckBox.isChecked():
                self.motor().moverel(self.targetDoubleSpinBox.value())
            else:
                self.motor().moveto(self.targetDoubleSpinBox.value())
        else:
            self.movePushButton.setEnabled(False)
            self.motor().stop()

    def onMotorStart(self, motor: Motor):
        if self._start_requested:
            self.setBusy()

    def onMotorSelected(self):
        self.setWindowTitle('Move motor {}'.format(self.motorComboBox.currentText()))
        for d in self.required_devices:
            self.unrequireDevice(d)
        self.required_devices = ['Motor_' + self.motorComboBox.currentText()]
        self.requireDevice(self.required_devices[0])
        motor = self.credo.motors[self.motorComboBox.currentText()]
        self.onMotorPositionChange(motor, motor.where())
        if self.relativeCheckBox.isChecked():
            self.targetDoubleSpinBox.setValue(0.0)
        else:
            self.targetDoubleSpinBox.setValue(motor.where())

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        self.positionLabel.setText('{:.4f}'.format(newposition))
        left = motor.get_variable('softleft')
        right = motor.get_variable('softright')
        if self.relativeCheckBox.isChecked():
            left -= newposition
            right -= newposition
        self.targetDoubleSpinBox.setMinimum(left)
        self.targetDoubleSpinBox.setMaximum(right)

    def onMotorStop(self, motor: Motor, targetpositionreached: bool):
        self.setIdle()
