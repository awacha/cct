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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._movephase = None
        self._movetarget = None
        logger.debug(str(self.__dict__.keys()))
        self.instrument.motors.newMotor.connect(self.onNewMotorConnected)

    def onNewMotorConnected(self, motorname: str):
        if motorname in [self.config['beamstop']['motorx'], self.config['beamstop']['motory']]:
            motor = self.instrument.motors[motorname]
            motor.started.connect(self.onMotorStarted)
            motor.stopped.connect(self.onMotorStopped)
            motor.positionChanged.connect(self.onMotorPositionChanged)

    def moveOut(self):
        self._movetarget = 'out'
        self.motorx().moveTo(self.config['beamstop']['out'][0])

    def moveIn(self):
        self._movetarget = 'in'
        self.motorx().moveTo(self.config['beamstop']['in'][0])

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
        elif self.motorx().isMoving() or self.motory().isMoving():
            self.state = self.States.Moving
        else:
            xpos = self.motorx().where()
            ypos = self.motory().where()
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
            if self.sender() == self.motorx():
                # movement of X motor is done, start with Y
                if success:
                    self.motory().moveTo(self.config['beamstop'][self._movetarget][1])
                else:
                    # not successful, break moving
                    self._movetarget = None
            elif self.sender() == self.motory():
                # moving the Y motor finished
                self._movetarget = None

    def onMotorPositionChanged(self, actualposition: float):
        self.checkState()

    def motorx(self) -> Motor:
        return self.instrument.motors[self.config['beamstop']['motorx']]

    def motory(self) -> Motor:
        return self.instrument.motors[self.config['beamstop']['motory']]

    def loadFromConfig(self):
        if 'motorx' not in self.config['beamstop']:
            self.config['beamstop']['motorx'] = 'BeamStop_X'
        if 'motory' not in self.config['beamstop']:
            self.config['beamstop']['motory'] = 'BeamStop_Y'

    def motorsAvailable(self) -> bool:
        return (self.config['beamstop']['motorx'] in self.instrument.motors) and (
                    self.config['beamstop']['motory'] in self.instrument.motors)
