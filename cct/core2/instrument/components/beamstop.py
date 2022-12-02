import enum
import logging
from typing import Optional, Tuple

import h5py
from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot

from .component import Component
from .motors import Motor, MotorRole, MotorDirection
from ...devices.device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BeamStop(Component, QtCore.QObject):
    class States(enum.Enum):
        In = 'in'
        Out = 'out'
        Undefined = 'undefined'
        Moving = 'moving'
        Error = 'error'

    stateChanged = Signal(str)
    movingFinished = Signal(bool)
    movingProgress = Signal(str, float, float, float)
    _movetarget: Optional[States]
    _movephase: Optional[str]
    state: States = States.Undefined
    motionstoprequested: bool = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._movephase = None
        self._movetarget = None
        logger.debug(str(self.__dict__.keys()))
        self.instrument.motors.newMotor.connect(self.onNewMotorConnected)

    @Slot()
    def onMotorDestroyed(self):
        # no need to disconnect signal handlers from the destroyed object: Qt does it automatically
        self.state = self.States.Undefined
        self.stateChanged.emit(self.state.value)

    def _disconnectMotor(self, motor: Motor):
        motor.started.disconnect(self.onMotorStarted)
        motor.stopped.disconnect(self.onMotorStopped)
        motor.moving.disconnect(self.onMotorMoving)
        motor.positionChanged.disconnect(self.onMotorPositionChanged)
        motor.destroyed.disconnect(self.onMotorDestroyed)
        motor.cameOnLine.disconnect(self.onMotorOnLine)
        motor.wentOffLine.disconnect(self.onMotorOffLine)

    def _connectMotor(self, motor: Motor):
        motor.started.connect(self.onMotorStarted)
        motor.stopped.connect(self.onMotorStopped)
        motor.moving.connect(self.onMotorMoving)
        motor.positionChanged.connect(self.onMotorPositionChanged)
        motor.destroyed.connect(self.onMotorDestroyed)
        motor.cameOnLine.connect(self.onMotorOnLine)
        motor.wentOffLine.connect(self.onMotorOffLine)

    @Slot()
    def onMotorOnLine(self):
        self.checkState()

    @Slot()
    def onMotorOffLine(self):
        self.state = self.States.Undefined
        self.stateChanged.emit(self.state.value)

    @Slot(str)
    def onNewMotorConnected(self, motorname: str):
        if self.instrument.motors.get(motorname).role == MotorRole.BeamStop:
            self._connectMotor(self.instrument.motors.get(motorname))

    def moveOut(self):
        if self._panicking != self.PanicState.NoPanic:
            raise RuntimeError('Cannot move beam-stop: panic!')
        self._movetarget = self.States.Out
        self.motionstoprequested = False
        self.motorx.moveTo(self.cfg['beamstop',  'out',  0])

    def moveIn(self):
        if self._panicking != self.PanicState.NoPanic:
            raise RuntimeError('Cannot move beam-stop: panic!')
        self._movetarget = self.States.In
        self.motionstoprequested = False
        self.motorx.moveTo(self.cfg['beamstop',  'in',  0])

    def calibrateIn(self, posx: float, posy: float):
        self.cfg['beamstop',  'in'] = (posx, posy)
        logger.info(f'Beamstop IN position changed to {posx:.4f}, {posy:.4f}')
        self.checkState()

    def calibrateOut(self, posx: float, posy: float):
        self.cfg['beamstop',  'out'] = (posx, posy)
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
            if (abs(xpos - self.cfg['beamstop',  'in',  0]) <= 0.0001) and \
                    (abs(ypos - self.cfg['beamstop',  'in',  1]) <= 0.0001):
                self.state = self.States.In
            elif (abs(xpos - self.cfg['beamstop',  'out',  0]) <= 0.0001) and \
                    (abs(ypos - self.cfg['beamstop',  'out',  1]) <= 0.0001):
                self.state = self.States.Out
            else:
                self.state = self.States.Undefined
        if self.state != oldstate:
            self.stateChanged.emit(self.state.value)
        return self.state

    @Slot(float, float, float)
    def onMotorMoving(self, current: float, start: float, end: float):
        if (self.state == self.States.Moving) and (self._movetarget is not None):
            self.movingProgress.emit(
                f'Moving beamstop {self._movetarget.value}, moving motor {self.sender().name}', start, end, current)

    @Slot(float)
    def onMotorStarted(self, startposition: float):
        self.checkState()

    @Slot(bool, float)
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
                    self.motory.moveTo(self.cfg['beamstop',  self._movetarget.value,  1])
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
        if self._panicking == self.PanicState.Panicking:
            super().panichandler()

    @Slot(float)
    def onMotorPositionChanged(self, actualposition: float):
        try:
            self.checkState()
        except DeviceFrontend.DeviceError:
            # can happen at the very beginning
            pass

    def motorsAvailable(self) -> bool:
        try:
            return self.instrument.motors.beamstop_x.isOnline() and self.instrument.motors.beamstop_y.isOnline()
        except KeyError:
            # happens when either of the motors is not present
            return False

    def stopMoving(self):
        if self._movetarget is not None:
            self.motory.stop()
            self.motorx.stop()

    def startComponent(self):
        for motor in self.instrument.motors.iterMotors():
            if motor.role == MotorRole.BeamStop:
                self._connectMotor(motor)
        super().startComponent()

    def stopComponent(self):
        try:
            self._disconnectMotor(self.motorx)
        except KeyError:
            pass
        try:
            self._disconnectMotor(self.motory)
        except KeyError:
            pass
        super().stopComponent()

    @property
    def motorx(self) -> Motor:
        return self.instrument.motors.beamstop_x

    @property
    def motory(self) -> Motor:
        return self.instrument.motors.beamstop_y

    def inPosition(self) -> Tuple[float, float]:
        return self.cfg['beamstop',  'in']

    def outPosition(self) -> Tuple[float, float]:
        return self.cfg['beamstop',  'out']

    def panichandler(self):
        self._panicking = self.PanicState.Panicking
        if self._movetarget is not None:
            self.stopMoving()
        else:
            super().panichandler()

    def toNeXus(self, instrumentgroup: h5py.Group) -> h5py.Group:
        bsgroup = instrumentgroup.require_group('beam_stop')  # the beamstop group will also be edited by the geometry component
        bsgroup.attrs['NX_class'] = 'NXbeam_stop'
        bsgroup.create_dataset('description', data='circular')
        bsgroup.create_dataset('status', data=self.state.value)
        wherex = self.motorx.where()
        wherey = self.motory.where()
        inx, iny = self.inPosition()
        bsgroup.create_dataset('x', data=wherex-inx).attrs.update({'units': 'mm'})
        bsgroup.create_dataset('y', data=wherey-iny).attrs.update({'units': 'mm'})
        return instrumentgroup

    def loadFromConfig(self):
        self.cfg.setdefault(('beamstop', 'in'), (0.0, 0.0))
        self.cfg.setdefault(('beamstop', 'out'), (0.0, 0.0))
        self.cfg.setdefault(('beamstop', 'motorx'), 'BeamStop_X')
        self.cfg.setdefault(('beamstop', 'motory'), 'BeamStop_Y')