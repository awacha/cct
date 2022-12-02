# coding: utf-8
"""Motor mover widget"""

import logging
from typing import Optional

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Slot

from .motormover_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.motors.motor import Motor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MotorMover(WindowRequiresDevices, QtWidgets.QWidget, Ui_Form):
    currentmotor: Optional[str] = None
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.motorNameComboBox.currentIndexChanged.connect(self.onMotorNameChanged)
        self.relativeMovementCheckBox.toggled.connect(self.onRelativeCheckBoxToggled)
        self.motorTargetDoubleSpinBox.lineEdit().returnPressed.connect(self.onMoveMotorClicked)
        self.motorNameComboBox.addItems([m.name for m in self.instrument.motors.iterMotors()])
        self.motorNameComboBox.setCurrentIndex(0)
        self.moveMotorPushButton.clicked.connect(self.onMoveMotorClicked)
        self.instrument.motors.newMotor.connect(self.onMotorAdded)
        self.instrument.motors.motorRemoved.connect(self.onMotorRemoved)

    @Slot(bool)
    def onRelativeCheckBoxToggled(self, toggled: Optional[bool] = None):
        if self.motorNameComboBox.currentIndex() < 0:
            self.moveMotorPushButton.setEnabled(False)
            return
        self.moveMotorPushButton.setEnabled(True)
        motor = self.instrument.motors.get(self.motorNameComboBox.currentText())
        if motor.isOnline():
            self.onMotorOnline()
            actualposition = motor.get('actualposition')
            left = motor.get('softleft')
            right = motor.get('softright')
            if toggled is None:
                toggled = self.relativeMovementCheckBox.isChecked()
            if toggled:
                self.motorTargetDoubleSpinBox.setRange(left - actualposition, right - actualposition)
                self.motorTargetDoubleSpinBox.setValue(0)
            else:
                self.motorTargetDoubleSpinBox.setRange(left, right)
                self.motorTargetDoubleSpinBox.setValue(actualposition)
        else:
            self.onMotorOffLine()
            self.motorTargetDoubleSpinBox.setRange(0,0)

    @Slot(int)
    def onMotorNameChanged(self, currentindex: int):
        if self.currentmotor is not None:
            self.disconnectMotor(self.currentmotor)
        self.currentmotor = self.motorNameComboBox.currentText()
        self.connectMotor(self.currentmotor)
        self.onRelativeCheckBoxToggled()  # this ensures setting the target spinbox limits and value.

    @Slot(float)
    def onMotorStarted(self, startposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        logger.debug(f'Motor {motor.name} started')
        if motor.name == self.motorNameComboBox.currentText():
            self.moveMotorPushButton.setText('Stop')
            self.moveMotorPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/stop.svg")))
            self.motorNameComboBox.setEnabled(False)
            self.motorTargetDoubleSpinBox.setEnabled(False)
            self.relativeMovementCheckBox.setEnabled(False)

    @Slot(float)
    def onMotorPositionChanged(self, newposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        if motor.name == self.motorNameComboBox.currentText():
            self.onRelativeCheckBoxToggled()

    @Slot(bool, float)
    def onMotorStopped(self, success: bool, endposition: float):
        motor = self.sender()
        assert isinstance(motor, Motor)
        logger.debug(f'Motor {motor.name} stopped')
        if motor.name == self.motorNameComboBox.currentText():
            self.moveMotorPushButton.setText('Move')
            self.moveMotorPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
            self.motorNameComboBox.setEnabled(True)
            self.motorTargetDoubleSpinBox.setEnabled(True)
            self.relativeMovementCheckBox.setEnabled(True)

    @Slot()
    def onMoveMotorClicked(self):
        motor = self.instrument.motors.get(self.motorNameComboBox.currentText())
        if self.moveMotorPushButton.text() == 'Move':
            if self.relativeMovementCheckBox.isChecked():
                motor.moveRel(self.motorTargetDoubleSpinBox.value())
            else:
                motor.moveTo(self.motorTargetDoubleSpinBox.value())
        elif self.moveMotorPushButton.text() == 'Stop':
            motor.stop()

    @Slot(str)
    def onMotorAdded(self, motorname: str):
        self.motorNameComboBox.blockSignals(True)
        try:
            currentmotor = self.motorNameComboBox.currentText()
            self.motorNameComboBox.clear()
            self.motorNameComboBox.addItems([m.name for m in self.instrument.motors.iterMotors()])
            self.motorNameComboBox.setCurrentIndex(self.motorNameComboBox.findText(currentmotor))
        finally:
            self.motorNameComboBox.blockSignals(False)
        if self.motorNameComboBox.currentText() != currentmotor:
            self.motorNameComboBox.setCurrentIndex(self.motorNameComboBox.currentIndex())

    @Slot(str)
    def onMotorRemoved(self, motorname: str):
        self.motorNameComboBox.blockSignals(True)
        try:
            currentmotor = self.motorNameComboBox.currentText()
            self.motorNameComboBox.clear()
            self.motorNameComboBox.addItems([m.name for m in self.instrument.motors.iterMotors()])
            self.motorNameComboBox.setCurrentIndex(self.motorNameComboBox.findText(currentmotor))
        finally:
            self.motorNameComboBox.blockSignals(False)
        if self.motorNameComboBox.currentText() != currentmotor:
            self.motorNameComboBox.setCurrentIndex(self.motorNameComboBox.currentIndex())

    @Slot()
    def onMotorOffLine(self):
        self.relativeMovementCheckBox.setEnabled(False)
        self.moveMotorPushButton.setEnabled(False)
        self.motorTargetDoubleSpinBox.setEnabled(False)

    @Slot()
    def onMotorOnline(self):
        self.relativeMovementCheckBox.setEnabled(True)
        self.moveMotorPushButton.setEnabled(True)
        self.motorTargetDoubleSpinBox.setEnabled(True)