import logging
from typing import Optional

from PyQt5 import QtCore

from .component import Component
from .motors import Motor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class BeamStop(QtCore.QObject, Component):
    class States:
        In = 'in'
        Out = 'out'
        Undefined = 'undefined'
        Moving = 'moving'

    stateChanged = QtCore.pyqtSignal(str)
    _movetarget: Optional[str]
    _movephase: Optional[str]
    state = States.Undefined
    motorx: Optional[Motor] = None
    motory: Optional[Motor] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._movephase = None
        self._movetarget = None
        logger.debug(str(self.__dict__.keys()))
        self.instrument.motors.newMotor.connect(self.onNewMotorConnected)

    def onNewMotorConnected(self):
        self.reConnectMotors()

    def moveOut(self):
        self._movetarget = 'out'
        self.motorx.moveTo(self.config['beamstop']['out'][0])

    def moveIn(self):
        self._movetarget = 'in'
        self.motorx.moveTo(self.config['beamstop']['in'][0])

    def calibrateIn(self, posx: float, posy: float):
        self.config['beamstop']['in'] = (posx, posy)
        logger.info(f'Beamstop IN position changed to {posx:.4f}, {posy:.4f}')
        self.checkState()

    def calibrateOut(self, posx: float, posy: float):
        self.config['beamstop']['out'] = (posx, posy)
        logger.info(f'Beamstop OUT position changed to {posx:.4f}, {posy:.4f}')
        self.checkState()

    def checkState(self) -> str:
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
            self.stateChanged.emit(self.state)
        return self.state

    def onMotorStarted(self, startposition: float):
        self.checkState()

    def onMotorStopped(self, success: bool, endposition: float):
        self.checkState()
        if self._movetarget is not None:
            if self.sender() == self.motorx:
                # movement of X motor is done, start with Y
                if success:
                    self.motory.moveTo(self.config['beamstop'][self._movetarget][1])
                else:
                    # not successful, break moving
                    self._movetarget = None
            elif self.sender() == self.motory:
                # moving the Y motor finished
                self._movetarget = None
        if self.stopping and (not self.motorx.isMoving()) and (not self.motory.isMoving()):
            self.stopComponent()

    def onMotorPositionChanged(self, actualposition: float):
        self.checkState()

    def loadFromConfig(self):
        if 'motorx' not in self.config['beamstop']:
            self.config['beamstop']['motorx'] = 'BeamStop_X'
        if 'motory' not in self.config['beamstop']:
            self.config['beamstop']['motory'] = 'BeamStop_Y'

    def motorsAvailable(self) -> bool:
        return (self.motorx is not None) and (self.motory is not None)

    def reConnectMotors(self):
        xname = self.config['beamstop']['motorx']
        yname = self.config['beamstop']['motory']
        for direction, newname in [('x', xname), ('y', yname)]:
            motor = self.motorx if direction == 'x' else self.motory
            if (motor is not None) and (motor.name == newname):
                # already connected, no change needed
                continue
            elif motor is not None:
                # disconnect the previous motor
                motor.started.disconnect(self.onMotorStarted)
                motor.stopped.disconnect(self.onMotorStopped)
                motor.positionChanged.disconnect(self.onMotorPositionChanged)
            try:
                motor = self.instrument.motors[newname]
            except KeyError:
                motor = None
            if motor is not None:
                motor.started.connect(self.onMotorStarted)
                motor.stopped.connect(self.onMotorStopped)
                motor.positionChanged.connect(self.onMotorPositionChanged)
            setattr(self, 'motorx' if direction == 'x' else 'motory', motor)

    def disconnectMotors(self):
        for motor in [self.motorx, self.motory]:
            if motor is None:
                continue
            motor.started.disconnect(self.onMotorStarted)
            motor.stopped.disconnect(self.onMotorStopped)
            motor.positionChanged.disconnect(self.onMotorPositionChanged)
        self.motorx = self.motory = None

    def startComponent(self):
        self.reConnectMotors()
        super().startComponent()

    def onConfigChanged(self, path, value):
        if (path == ('beamstop', 'motory')) or (path == ('beamstop', 'motorx')):
            self.reConnectMotors()

    def stopComponent(self):
        self.disconnectMotors()
        super().stopComponent()
