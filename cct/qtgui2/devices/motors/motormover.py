# coding: utf-8
"""Motor mover widget"""

import logging
from typing import Optional

from PyQt5 import QtWidgets, QtGui

from .motormover_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.motors.motor import Motor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class MotorMover(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.motorNameComboBox.currentIndexChanged.connect(self.onMotorNameChanged)
        self.relativeMovementCheckBox.toggled.connect(self.onRelativeCheckBoxToggled)
        self.motorTargetDoubleSpinBox.lineEdit().returnPressed.connect(self.onMoveMotorClicked)
        self.motorNameComboBox.addItems([m.name for m in self.instrument.motors.motors])
        self.motorNameComboBox.setCurrentIndex(0)
        self.moveMotorPushButton.clicked.connect(self.onMoveMotorClicked)
        self.moveMotorPushButton.setEnabled(False)

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
            self.moveMotorPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/stop.svg")))
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
            self.moveMotorPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
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
