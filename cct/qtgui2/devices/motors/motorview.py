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
    required_motors = ['*']

    def __init__(self, **kwargs):
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
        self.beamStopInXDoubleSpinBox.setValue(self.instrument.beamstop.inPosition()[0])
        self.beamStopInYDoubleSpinBox.setValue(self.instrument.beamstop.inPosition()[1])
        self.beamStopOutXDoubleSpinBox.setValue(self.instrument.beamstop.outPosition()[0])
        self.beamStopOutYDoubleSpinBox.setValue(self.instrument.beamstop.outPosition()[1])
        self.calibrateBeamStopInPushButton.clicked.connect(self.calibrateBeamStopIn)
        self.calibrateBeamStopOutPushButton.clicked.connect(self.calibrateBeamStopOut)
        self.moveBeamStopInPushButton.clicked.connect(self.instrument.beamstop.moveIn)
        self.moveBeamStopOutPushButton.clicked.connect(self.instrument.beamstop.moveOut)
        self.beamStopOutYDoubleSpinBox.valueChanged.connect(self.onBeamStopCoordinateSpinBoxChanged)
        self.beamStopOutXDoubleSpinBox.valueChanged.connect(self.onBeamStopCoordinateSpinBoxChanged)
        self.beamStopInYDoubleSpinBox.valueChanged.connect(self.onBeamStopCoordinateSpinBoxChanged)
        self.beamStopInXDoubleSpinBox.valueChanged.connect(self.onBeamStopCoordinateSpinBoxChanged)

    def onBeamStopCoordinateSpinBoxChanged(self):
        if self.sender() is self.beamStopInXDoubleSpinBox:
            inpos = self.instrument.beamstop.inPosition()
            self.instrument.beamstop.calibrateIn(self.sender().value(), inpos[1])
        elif self.sender() is self.beamStopInYDoubleSpinBox:
            inpos = self.instrument.beamstop.inPosition()
            self.instrument.beamstop.calibrateIn(inpos[0], self.sender().value())
        elif self.sender() is self.beamStopOutXDoubleSpinBox:
            outpos = self.instrument.beamstop.outPosition()
            self.instrument.beamstop.calibrateOut(self.sender().value(), outpos[1])
        elif self.sender() is self.beamStopOutYDoubleSpinBox:
            outpos = self.instrument.beamstop.outPosition()
            self.instrument.beamstop.calibrateOut(outpos[0], self.sender().value())

    def _calibrateBeamstop(self, out:bool=False):
        posx, posy = self.instrument.motors.beamstop_x.where(), self.instrument.motors.beamstop_y.where()
        if QtWidgets.QMessageBox.question(
                self, 'Confirm beamstop calibration',
                f'Do you really want to calibrate the beamstop {"out" if out else "in"} position '
                f'to ({posx:.4f}, {posy:.4f})?'):
            widgets = [self.beamStopOutXDoubleSpinBox, self.beamStopOutYDoubleSpinBox] if out else [self.beamStopInXDoubleSpinBox, self.beamStopInYDoubleSpinBox]
            for w in widgets:
                w.blockSignals(True)
            widgets[0].setValue(posx)
            widgets[1].setValue(posy)
            if out:
                self.instrument.beamstop.calibrateOut(posx, posy)
            else:
                self.instrument.beamstop.calibrateIn(posx, posy)
            for w in widgets:
                w.blockSignals(False)

    def calibrateBeamStopIn(self):
        self._calibrateBeamstop(False)

    def calibrateBeamStopOut(self):
        self._calibrateBeamstop(True)

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
        self.onRelativeCheckBoxToggled()  # this ensures setting the target spinbox limits and value.

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
