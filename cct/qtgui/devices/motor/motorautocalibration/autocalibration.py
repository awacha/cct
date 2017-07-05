from typing import Union

from PyQt5 import QtWidgets, QtGui, QtCore

from .autocalibration_ui import Ui_Form
from .autocalibrationmodel import MotorAutoCalibrationModel
from ....core.mixins import ToolWindow
from .....core.devices import Device
from .....core.devices.motor import Motor
from .....core.instrument.privileges import PRIV_MOTORCALIB
from .....core.utils.inhibitor import Inhibitor


class MotorAutoCalibration(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_privilege = PRIV_MOTORCALIB
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo=credo)
        self.setupUi(self)
        self._updating=Inhibitor()
        self._motor_under_calibration = None
        self._calibration_phase = None
        self._startpos_old_coordinates = None
        self._moved_left = None
        self._stop_requested = False

    def setupUi(self, Form):
        Ui_Form.setupUi(self, self)
        self.addMotorComboBox.currentIndexChanged.connect(self.onAddMotor)
        self.removeMotorPushButton.clicked.connect(self.onRemoveMotor)
        self.executePushButton.clicked.connect(self.onExecute)
        with self._updating:
            self.addMotorComboBox.clear()
            self.addMotorComboBox.addItems(sorted([m.name for m in self.credo.motors.values()]))
            self.addMotorComboBox.setCurrentIndex(-1)
        self.model = MotorAutoCalibrationModel(self.credo)
        self.motorTreeView.setModel(self.model)

    def onAddMotor(self):
        if self._updating:
            return
        with self._updating:
            motname = self.addMotorComboBox.currentText()
            if motname not in self.model:
                self.model.addMotor(self.addMotorComboBox.currentText())
                self.requireDevice('Motor_'+motname)
            self.addMotorComboBox.setCurrentIndex(-1)

    def onRemoveMotor(self):
        rowindex = self.motorTreeView.selectionModel().selectedRows()[0]
        assert isinstance(rowindex, QtCore.QModelIndex)
        self.model.removeRow(rowindex.row(), QtCore.QModelIndex())

    def onExecute(self):
        if self.executePushButton.text()=='Execute':
            self._stop_requested=False
            self.model.resetCalibrationData()
            self.setBusy()
            self.nextMotor()
        else:
            # stop
            pass

    def nextMotor(self):
        if self._stop_requested:
            self.setIdle()
            return
        self._motor_under_calibration = self.model.nextMotor()
        self.model.resetCalibrationData(self._motor_under_calibration)
        self._calibration_phase = 'CalibrateToRight'
        motor = self.credo.motors[self._motor_under_calibration]
        self._startpos_old_coordinates = motor.where()
        self._moved_left = 0
        assert isinstance(motor, Motor)
        motor.calibrate(motor.get_variable('softright'))

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        if motor.name not in self.model:
            return False
        self.model.updateMotorPosition(motor.name, newposition)
        if ((self._calibration_phase == 'CalibrateToRight') and
                (self._motor_under_calibration == motor.name) and
                (abs(newposition-motor.get_variable('softright'))<0.00001)):
            # the calibration of the current motor to the right limit finished.
            # We need to move it as much left as we can.
            self._calibration_phase = 'MoveLeft'
            motor.moveto(motor.get_variable('softleft'))
        elif ((self._calibration_phase == 'CalibrateBeforeMoveSlightlyRight') and
                (self._motor_under_calibration == motor.name) and
                (abs(newposition-motor.get_variable('softleft'))<0.00001)):
            # Moving the motor slightly right
            self._calibration_phase = 'MoveSlightlyRight'
            motor.moverel(self.bufferDistanceDoubleSpinBox.value())
        elif ((self._calibration_phase == 'FinalCalibrationToLeftLimit') and
                (self._motor_under_calibration == motor.name) and
                (abs(newposition-motor.get_variable('softleft'))<0.00001)):
            # Move back to the starting point.
            self._calibration_phase = 'MoveBackToStart'
            motor.moverel(-self._moved_left)
        return False

    def onDeviceVariableChange(self, device: Union[Device, Motor], variablename: str, newvalue):
        if device.name not in self.model:
            return False
        if variablename == 'softleft':
            self.model.updateMotorLeftLimit(device.name, newvalue)
        elif variablename == 'softright':
            self.model.updateMotorRightLimit(device.name, newvalue)
        return False

    def onMotorStop(self, motor: Motor, targetpositionreached: bool):
        if ((self._calibration_phase == 'MoveLeft') and
                (self._motor_under_calibration == motor.name)):
            self._moved_left = motor.where() - self._startpos_old_coordinates
            if not motor.leftlimitswitch():
                # should not happen normally.
                QtWidgets.QMessageBox.critical(self, 'Error', 'Left limit switch not reached!')
                self.setIdle()
            self._calibration_phase = 'CalibrateBeforeMoveSlightlyRight'
            motor.calibrate(motor.get_variable('softleft'))
        elif ((self._calibration_phase == 'MoveSligthlyRight') and
                  (self._motor_under_calibration == motor.name)):
            self._moved_left += self.bufferDistanceDoubleSpinBox.value()
            self._calibration_phase = 'FinalCalibrationToLeftLimit'
            motor.calibrate(motor.get_variable('softleft'))
        elif ((self._calibration_phase == 'MoveBackToStart') and
                  (self._motor_under_calibration == motor.name)):
            # finished.
            self.model.updateMotorPositionAfter(motor.name, motor.where())
            self.model.calculateMotorDelta(motor.name)
            self.nextMotor()
        return False

    def setIdle(self):
        super().setIdle()
        self.addMotorComboBox.setEnabled(True)
        self.bufferDistanceDoubleSpinBox.setEnabled(True)
        self.motorTreeView.setEnabled(True)
        self.removeMotorPushButton.setEnabled(True)
        self.executePushButton.setText('Execute')
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/motorconfig.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.executePushButton.setIcon()

    def setBusy(self):
        self.addMotorComboBox.setEnabled(False)
        self.bufferDistanceDoubleSpinBox.setEnabled(False)
        self.motorTreeView.setEnabled(False)
        self.removeMotorPushButton.setEnabled(False)
        self.executePushButton.setText('Stop')
        self.executePushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
        super().setBusy()
