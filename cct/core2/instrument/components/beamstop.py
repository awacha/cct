import logging
from typing import Optional, Tuple
import enum

from PyQt5 import QtCore

from .component import Component
from .motors import Motor, MotorRole, MotorDirection
from ...devices.device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BeamStop(QtCore.QObject, Component):
    class States(enum.Enum):
        In = 'in'
        Out = 'out'
        Undefined = 'undefined'
        Moving = 'moving'
        Error = 'error'

    stateChanged = QtCore.pyqtSignal(str)
    movingFinished = QtCore.pyqtSignal(bool)
    movingProgress = QtCore.pyqtSignal(str, float, float, float)
    _movetarget: Optional[States]
    _movephase: Optional[str]
    state:States = States.Undefined
    xmotorname: Optional[str] = None
    ymotorname: Optional[str] = None
    motionstoprequested: bool=False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._movephase = None
        self._movetarget = None
        logger.debug(str(self.__dict__.keys()))
        self.instrument.motors.newMotor.connect(self.onNewMotorConnected)

    def onMotorDestroyed(self):
        motor = self.sender()
        assert isinstance(motor, Motor)
        if motor.name == self.xmotorname:
            self.xmotorname = None
        elif motor.name == self.ymotorname:
            self.ymotorname = None
        self.state = self.States.Undefined
        self.stateChanged.emit(self.state.value)
        return

    def _disconnectMotor(self, motor:Motor):
        motor.started.disconnect(self.onMotorStarted)
        motor.stopped.disconnect(self.onMotorStopped)
        motor.moving.disconnect(self.onMotorMoving)
        motor.positionChanged.disconnect(self.onMotorPositionChanged)
        motor.destroyed.disconnect(self.onMotorDestroyed)

    def _connectMotor(self, motor:Motor):
        motor.started.connect(self.onMotorStarted)
        motor.stopped.connect(self.onMotorStopped)
        motor.moving.connect(self.onMotorMoving)
        motor.positionChanged.connect(self.onMotorPositionChanged)
        motor.destroyed.connect(self.onMotorDestroyed)

    def reConnectMotors(self):
        if (self.xmotorname is not None) and (self.instrument.motors.beamstop_x.name != self.xmotorname):
            # motor has changed, disconnect the previous motor
            motor = self.instrument.motors[self.xmotorname]
            self._disconnectMotor(self.instrument.motors[self.xmotorname])
            self.xmotorname = None
        if (self.ymotorname is not None) and (self.instrument.motors.beamstop_y.name != self.ymotorname):
            # motor has changed, disconnect the previous motor
            motor = self.instrument.motors[self.ymotorname]
            self._disconnectMotor(self.instrument.motors[self.ymotorname])
            self.ymotorname = None
        if self.xmotorname is None:
            try:
                self.xmotorname = self.instrument.motors.beamstop_x.name
                self._connectMotor(self.instrument.motors.beamstop_x)
            except KeyError:
                self.xmotorname = None
        if self.ymotorname is None:
            try:
                self.ymotorname = self.instrument.motors.beamstop_y.name
                self._connectMotor(self.instrument.motors.beamstop_y)
            except KeyError:
                self.ymotorname = None

    def onNewMotorConnected(self, motorname: str):
        self.reConnectMotors()

    def moveOut(self):
        self._movetarget = self.States.Out
        self.motionstoprequested = False
        self.motorx.moveTo(self.config['beamstop']['out'][0])

    def moveIn(self):
        self._movetarget = self.States.In
        self.motionstoprequested = False
        self.motorx.moveTo(self.config['beamstop']['in'][0])

    def calibrateIn(self, posx: float, posy: float):
        self.config['beamstop']['in'] = (posx, posy)
        logger.info(f'Beamstop IN position changed to {posx:.4f}, {posy:.4f}')
        self.checkState()

    def calibrateOut(self, posx: float, posy: float):
        self.config['beamstop']['out'] = (posx, posy)
        logger.info(f'Beamstop OUT position changed to {posx:.4f}, {posy:.4f}')
        self.checkState()

    def checkState(self) -> States:
        oldstate = self.state
        if not self.motorsAvailable():
            self.state = self.States.Undefined
        elif self.motorx.isMoving() or self.motory.isMoving():
            self.state = self.States.Moving
        else:
            xpos = self.motorx.where()
            ypos = self.motory.where()
            if (abs(xpos - self.config['beamstop']['in'][0]) <= 0.0001) and \
                    (abs(ypos - self.config['beamstop']['in'][1]) <= 0.0001):
                self.state = self.States.In
            elif (abs(xpos - self.config['beamstop']['out'][0]) <= 0.0001) and \
                    (abs(ypos - self.config['beamstop']['out'][1]) <= 0.0001):
                self.state = self.States.Out
            else:
                self.state = self.States.Undefined
        if self.state != oldstate:
            self.stateChanged.emit(self.state.value)
        return self.state

    def onMotorMoving(self, current: float, start: float, end: float):
        if self.state == self.States.Moving:
            self.movingProgress.emit(
                f'Moving beamstop {self._movetarget.value}, moving motor {self.sender().name}', start, end, current)

    def onMotorStarted(self, startposition: float):
        self.checkState()

    def onMotorStopped(self, success: bool, endposition: float):
        self.checkState()
        motor = self.sender()
        assert isinstance(motor, Motor)
        if self._movetarget is not None:
            if self.motionstoprequested:
                self.movingFinished.emit(False)
            elif (motor.role == MotorRole.BeamStop) and (motor.direction == MotorDirection.X):
                # movement of X motor is done, start with Y
                if success:
                    self.motory.moveTo(self.config['beamstop'][self._movetarget.value][1])
                else:
                    # not successful, break moving
                    logger.error('Error while moving beam-stop: target not reached.')
                    self.movingFinished.emit(False)
                    self._movetarget = None
            elif (motor.role == MotorRole.BeamStop) and (motor.direction == MotorDirection.Y):
                # moving the Y motor finished
                self._movetarget = None
                self.movingFinished.emit(True)
        if self.stopping and (not self.motorx.isMoving()) and (not self.motory.isMoving()):
            self.stopComponent()

    def onMotorPositionChanged(self, actualposition: float):
        try:
            self.checkState()
        except DeviceFrontend.DeviceError:
            # can happen at the very beginning
            pass

    def motorsAvailable(self) -> bool:
        return (self.xmotorname is not None) and (self.ymotorname is not None)

    def stopMoving(self):
        if self._movetarget is not None:
            self.motory.stop()
            self.motorx.stop()

    def disconnectMotors(self):
        for motorname in [self.xmotorname, self.ymotorname]:
            if motorname is None:
                continue
            try:
                motor = self.instrument.motors[motorname]
            except KeyError:
                pass
            self._disconnectMotor(motor)

    def startComponent(self):
        self.reConnectMotors()
        super().startComponent()

    def stopComponent(self):
        self.disconnectMotors()
        super().stopComponent()

    @property
    def motorx(self) -> Motor:
        return self.instrument.motors.beamstop_x

    @property
    def motory(self) -> Motor:
        return self.instrument.motors.beamstop_y

    def inPosition(self) -> Tuple[float, float]:
        return self.config['beamstop']['in']

    def outPosition(self) -> Tuple[float, float]:
        return self.config['beamstop']['out']
