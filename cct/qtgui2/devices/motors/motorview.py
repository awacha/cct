import logging
from typing import Optional

from PyQt5 import QtWidgets, QtGui

from .motorview_ui import Ui_Form
from .addmotordialog import AddMotorDialog
from .motorcalibration import MotorCalibrationDialog
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.motors import Motor
from ....core2.instrument.components.auth.privilege import Privilege
from .autoadjust import AutoAdjustMotor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class MotorView(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    addMotorDialog: Optional[AddMotorDialog] = None
    motorCalibrationDialog: Optional[MotorCalibrationDialog] = None

    def __init__(self, **kwargs):
        self.required_motors = [m.name for m in kwargs['instrument'].motors.motors]
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.motors)
        self.motorNameComboBox.currentIndexChanged.connect(self.onMotorNameChanged)
        self.relativeMovementCheckBox.toggled.connect(self.onRelativeCheckBoxToggled)
        self.motorTargetDoubleSpinBox.lineEdit().returnPressed.connect(self.onMoveMotorClicked)
        self.motorNameComboBox.addItems([m.name for m in self.instrument.motors.motors])
        self.motorNameComboBox.setCurrentIndex(0)
        self.moveMotorPushButton.clicked.connect(self.onMoveMotorClicked)
        self.addMotorToolButton.clicked.connect(self.addMotor)
        self.removeMotorToolButton.clicked.connect(self.removeMotor)
        self.calibrateMotorToolButton.clicked.connect(self.calibrateMotor)
        self.autoAdjustMotorToolButton.clicked.connect(self.autoAdjustMotor)

    def addMotor(self):
        if not self.instrument.auth.hasPrivilege(Privilege.MotorConfiguration):
            QtWidgets.QMessageBox.critical(self, 'Insufficient privileges', 'Insufficient privileges to add a motor.')
            return
        self.addMotorDialog = AddMotorDialog(parent=self)
        self.addMotorDialog.finished.connect(self.onAddMotorDialogFinished)
        self.addMotorDialog.show()

    def onAddMotorDialogFinished(self, accepted: bool):
        if accepted:
            self.instrument.motors.addMotor(
                self.addMotorDialog.motorName(),
                self.addMotorDialog.controllerName(),
                self.addMotorDialog.axis(),
                self.addMotorDialog.leftlimit(),
                self.addMotorDialog.rightlimit(),
                self.addMotorDialog.position()
            )
        self.addMotorDialog.finished.disconnect(self.onAddMotorDialogFinished)
        self.addMotorDialog.close()
        self.addMotorDialog.deleteLater()
        self.addMotorDialog = None

    def removeMotor(self):
        index = self.treeView.selectionModel().currentIndex()
        if not index.isValid():
            return
        if not self.instrument.auth.hasPrivilege(Privilege.MotorConfiguration):
            QtWidgets.QMessageBox.critical(self, 'Insufficient privileges', 'Cannot remove motor: not enough privileges.')
            return
        self.instrument.motors.removeMotor(self.instrument.motors[index.row()].name)

    def calibrateMotor(self):
        if not self.instrument.auth.hasPrivilege(Privilege.MotorCalibration):
            QtWidgets.QMessageBox.critical(
                self, "Insufficient privileges", "Cannot calibrate motor: insufficient privileges")
            return
        self.motorCalibrationDialog = MotorCalibrationDialog(
            parent=self,
            motorname=self.instrument.motors[self.treeView.selectionModel().currentIndex().row()].name)
        self.motorCalibrationDialog.finished.connect(self.onMotorCalibrationDialogFinished)
        self.motorCalibrationDialog.show()

    def onMotorCalibrationDialogFinished(self, accepted: bool):
        if accepted:
            motor = self.instrument.motors[self.motorCalibrationDialog.motorname]
            motor.setLimits(self.motorCalibrationDialog.leftLimit(), self.motorCalibrationDialog.rightLimit())
            motor.setPosition(self.motorCalibrationDialog.position())
        self.motorCalibrationDialog.close()
        self.motorCalibrationDialog.deleteLater()
        self.motorCalibrationDialog = None

    def autoAdjustMotor(self):
        if not self.treeView.selectionModel().currentIndex().isValid():
            return
        if not self.instrument.auth.hasPrivilege(Privilege.MotorCalibration):
            QtWidgets.QMessageBox.critical(self, 'Insufficient privileges to calibrate motors.')
            return
        win = self.mainwindow.addSubWindow(AutoAdjustMotor, singleton=False)
        if win is None:
            return
        win.setMotor(self.instrument.motors[self.treeView.selectionModel().currentIndex().row()].name)

    def onRelativeCheckBoxToggled(self, toggled: Optional[bool] = None):
        if self.motorNameComboBox.currentIndex() < 0:
            return
        motor = self.instrument.motors[self.motorNameComboBox.currentText()]
        actualposition = motor['actualposition']
        left = motor['softleft']
        right = motor['softright']
        if toggled is None:
            toggled = self.relativeMovementCheckBox.isChecked()
        if toggled:
            self.motorTargetDoubleSpinBox.setRange(left - actualposition, right - actualposition)
            self.motorTargetDoubleSpinBox.setValue(0)
        else:
            self.motorTargetDoubleSpinBox.setRange(left, right)
            self.motorTargetDoubleSpinBox.setValue(actualposition)

    def onMotorNameChanged(self, currentindex: int):
        motor = self.instrument.motors[self.motorNameComboBox.currentText()]
        self.onRelativeCheckBoxToggled()

    def onMotorStarted(self, startposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        logger.debug(f'Motor {motor.name} started')
        if motor.name == self.motorNameComboBox.currentText():
            self.moveMotorPushButton.setText('Stop')
            self.moveMotorPushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
            self.motorNameComboBox.setEnabled(False)
            self.motorTargetDoubleSpinBox.setEnabled(False)
            self.relativeMovementCheckBox.setEnabled(False)

    def onMotorPositionChanged(self, newposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        if motor.name == self.motorNameComboBox.currentText():
            self.onRelativeCheckBoxToggled()

    def onMotorStopped(self, success: bool, endposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        logger.debug(f'Motor {motor.name} stopped')
        if motor.name == self.motorNameComboBox.currentText():
            self.moveMotorPushButton.setText('Move')
            self.moveMotorPushButton.setIcon(QtGui.QIcon.fromTheme('system-run'))
            self.motorNameComboBox.setEnabled(True)
            self.motorTargetDoubleSpinBox.setEnabled(True)
            self.relativeMovementCheckBox.setEnabled(True)

    def onMoveMotorClicked(self):
        motor = self.instrument.motors[self.motorNameComboBox.currentText()]
        if self.moveMotorPushButton.text() == 'Move':
            if self.relativeMovementCheckBox.isChecked():
                motor.moveRel(self.motorTargetDoubleSpinBox.value())
            else:
                motor.moveTo(self.motorTargetDoubleSpinBox.value())
        elif self.moveMotorPushButton.text() == 'Stop':
            motor.stop()

    def onCommandResult(self, name: str, success: str, message: str):
        pass
