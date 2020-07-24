import logging
import os
from typing import Tuple, Any

from PyQt5 import QtCore

from ...device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class MotorController(DeviceFrontend):
    Naxes: int
    moveStarted = QtCore.pyqtSignal(int, float)
    moveEnded = QtCore.pyqtSignal(int, bool, float)
    devicetype = 'motorcontroller'
    devicename = ''

    def __init__(self, name: str, host: str, port: int):
        self._backendkwargs = {'positionfile': os.path.join('config', f'{name}.motorpos')}

        super().__init__(name, host, port)
        self.Naxes = self.backendclass.Naxes

    def moveTo(self, motor: int, position: float):
        if position < self[f'softleft${motor}'] or position > self[f'softright${motor}']:
            raise self.DeviceError(f'Cannot move motor {motor}: position outside limits.')
        if self[f'moving${motor}']:
            raise self.DeviceError(f'Cannot move motor {motor}: already in motion.')
        self.issueCommand('moveto', motor, position)

    def moveRel(self, motor: int, position: float):
        if (self[f'actualposition${motor}'] + position < self[f'softleft${motor}']) or \
                (self[f'actualposition${motor}'] + position > self[f'softright${motor}']):
            raise self.DeviceError(f'Cannot move motor {motor}: position outside limits.')
        if self[f'moving${motor}']:
            raise self.DeviceError(f'Cannot move motor {motor}: already in motion.')
        self.issueCommand('moverel', motor, position)

    def stopMotor(self, motor: int):
        self.issueCommand('stop', motor)

    def setPosition(self, motor: int, position: float):
        self.issueCommand('setposition', motor, position)

    def setLimits(self, motor: int, left: float, right: float):
        self.issueCommand('setlimits', motor, (left, right))

    def getLimits(self, motor: int) -> Tuple[float, float]:
        return self[f'softleft${motor}'], self[f'softright${motor}']

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        varbasename = variablename.split('$')[0]
        if varbasename == 'moving':
            axis = int(variablename.split('$')[-1])
            try:
                if newvalue:
                    self.moveStarted.emit(axis, self[f'movestartposition${axis}'])
                else:
                    self.moveEnded.emit(axis, self[f'lastmovewassuccessful${axis}'], self[f'actualposition${axis}'])
            except self.DeviceError:
                # this error is normal if not all variables have been updated.
                if self.ready:
                    raise
