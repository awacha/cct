import enum
from typing import Optional
import logging

from PyQt5 import QtWidgets, QtGui
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.motors.motor import Motor
from .autoadjust_ui import Ui_Form

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AdjustingState(enum.Enum):
    WaitForInitialSetPositionResult = 1
    MovingLeft = 2
    MoveByBufferDistance = 3
    WaitForFinalSetPositionResult = 4
    MovingRight = 5
    Idle = 0
    Stopping = -1


class AutoAdjustMotor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    """Steps of motor auto-adjustment:

    1. remember the current motor position (-> oldposition)
    2. calibrate the motor to the current right position
    3. move motor to the left position
    4. when it stops (probably not at the left position, named as -> leftposition): move right by "bufferdistance"
    5. set the current position to the left limit
    6. move back to the original position.
    7. report the difference

    Coordinates

    Before step 1  | After step 2               |  After step 5
    ==============================================================
    oldposition    | softright                  |
                   | leftposition + bufferdist  |  softleft

    oldposition with the new reference point:
        softright - leftposition - bufferdist + softleft
    delta: (softright - leftposition - bufferdist + softleft - oldposition)

    """
    oldposition: Optional[float] = None
    leftposition: Optional[float] = None
    motorname: Optional[str] = None
    state: AdjustingState = AdjustingState.Idle
    delta: Optional[float] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.motorNameComboBox.currentIndexChanged.connect(self.onMotorChanged)
        self.motorNameComboBox.addItems(sorted([m.name for m in self.instrument.motors]))
        self.startPushButton.clicked.connect(self.onStartClicked)
        self.progressBar.setVisible(False)
        self.resize(self.minimumSize())

    def motor(self) -> Motor:
        return self.instrument.motors[self.motorname]

    def setMotor(self, motorname: str):
        if self.state != AdjustingState.Idle:
            raise RuntimeError('Cannot change motor while not idle.')
        self.motorname = motorname
        self.motorNameComboBox.setCurrentIndex(self.motorNameComboBox.findText(motorname))
        self.onMotorChanged()

    def onStartClicked(self):
        if self.startPushButton.text() == 'Start':
            if self.state != AdjustingState.Idle:
                QtWidgets.QMessageBox.critical(
                    self, 'Error', 'Cannot start auto-adjustment: auto-adjustment is already running')
            elif self.motor().isMoving():
                QtWidgets.QMessageBox.critical(
                    self, 'Error', 'Cannot start auto-adjustment: motor is moving.'
                )
            self.oldposition = self.motor().where()
            self.motor().setPosition(self.motor()['softright'])
            self.state = AdjustingState.WaitForInitialSetPositionResult
            logger.debug('Autoadjust #1: setting motor position to right')
            self.startPushButton.setText('Stop')
            self.startPushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
        elif self.startPushButton.text() == 'Stop':
            self.state = AdjustingState.Stopping
            self.motor().stop()

    def onMotorChanged(self):
        if self.motorname is not None:
            try:
                self.disconnectMotor(self.instrument.motors[self.motorname])
            except TypeError:
                pass
        self.motorname = None if self.motorNameComboBox.currentIndex() < 0 else self.motorNameComboBox.currentText()
        self.connectMotor(self.instrument.motors[self.motorname])

    def onMotorPositionChanged(self, newposition: float):
        if (self.state == AdjustingState.WaitForInitialSetPositionResult) and \
                (newposition == self.motor()['softright']):
            logger.debug('AutoAdjust #1 acknowledged. Now moving left.')
            self.state = AdjustingState.MovingLeft
            self.motor().moveTo(self.motor()['softleft'])
        elif (self.state == AdjustingState.WaitForFinalSetPositionResult) and \
                (newposition == self.motor()['softleft']):
            self.state = AdjustingState.MovingRight
            self.delta = (self.motor()['softright'] - self.leftposition - self.bufferDistanceDoubleSpinBox.value() + \
                          self.motor()['softleft'] - self.oldposition)
            self.motor().moveTo(self.oldposition + self.delta)

    def onMotorMoving(self, position: float, startposition: float, endposition: float):
        logger.debug(f'onMotorMoving({position}, {startposition}, {endposition}); state={self.state.value}')
        if self.state in [AdjustingState.MovingLeft, AdjustingState.MovingRight, AdjustingState.MoveByBufferDistance]:
            self.progressBar.setVisible(True)
            self.progressBar.setRange(0, 1000)
            self.progressBar.setValue(int(1000*(position-startposition) / (endposition-startposition)))
            self.progressBar.setFormat(f'Moving motor {self.motor().name} to {endposition:.4f}')

    def onMotorStopped(self, success: bool, endposition: float):
        motor = self.motor()
        assert self.sender() is motor
        if self.state == AdjustingState.Stopping:
            self.finalize()
            return
        elif self.state == AdjustingState.MovingLeft:
            if success or (not motor['leftswitchstatus']):
                QtWidgets.QMessageBox.critical(self, 'Error', 'Left switch not hit.')
                self.finalize()
                return
            # stopped on left limit switch
            logger.debug(f'Stopped on left limit switch at position {motor.where()}')
            self.state = AdjustingState.MoveByBufferDistance
            self.leftposition = motor.where()
            logger.debug(f'Moving right by bufferdistance {self.bufferDistanceDoubleSpinBox.value()}')
            motor.moveRel(self.bufferDistanceDoubleSpinBox.value())
            logger.debug(f'Moverel issued.')
        elif self.state == AdjustingState.MoveByBufferDistance:
            if not success:
                QtWidgets.QMessageBox.critical(
                    self, 'Error', f'Cannot move right by buffer distance {self.bufferDistanceDoubleSpinBox.value()}')
                self.finalize()
                return
            logger.debug('Moving by buffer distance done.')
            motor.setPosition(motor['softleft'])
            self.state = AdjustingState.WaitForFinalSetPositionResult
        elif self.state == AdjustingState.MovingRight:
            if not success:
                QtWidgets.QMessageBox.critical(self, 'Error', f'Cannot reach original position.')
                self.finalize()
                return
            self.state = AdjustingState.Idle
            QtWidgets.QMessageBox.information(
                self, 'Success', f'Motor auto-adjustment successful. Delta is {self.delta}.')
            self.finalize()

    def finalize(self):
        self.state = AdjustingState.Idle
        self.oldposition = None
        self.leftposition = None
        self.delta = None
        for widget in [self.bufferDistanceDoubleSpinBox, self.motorNameComboBox]:
            widget.setEnabled(True)
        self.progressBar.setVisible(False)
        self.startPushButton.setText('Start')
        self.startPushButton.setIcon(QtGui.QIcon.fromTheme('system-run'))
