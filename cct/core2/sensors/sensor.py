import enum
import logging
import math
from typing import Optional, Dict, Any

import numpy as np
from PyQt5 import QtCore

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ErrorState(enum.Enum):
    OK = 0
    Warning = 1
    Error = 2
    Unknown = 3


class Sensor(QtCore.QObject):
    name: str
    sensortype: str
    quantityname: str
    devicename: str
    index: int
    valueChanged = QtCore.pyqtSignal(float)
    _value: float
    units: str
    lowwarnlimit: Optional[float] = None
    highwarnlimit: Optional[float] = None
    lowerrorlimit: Optional[float] = None
    higherrorlimit: Optional[float] = None
    paniconerror: bool
    _errorstate: ErrorState = ErrorState.Unknown

    warning = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal()
    ok = QtCore.pyqtSignal()
    unknown = QtCore.pyqtSignal()

    def __init__(self, name: str, devicename: str, index: int, units: str, lowwarnlimit: Optional[float] = None,
                 highwarnlimit: Optional[float] = None, lowerrorlimit: Optional[float] = None,
                 higherrorlimit: Optional[float] = None, paniconerror: bool=False):
        self._value = math.nan
        self.name = name
        self.devicename = devicename
        self.index = index
        self.units = units
        self.lowwarnlimit = lowwarnlimit
        self.highwarnlimit = highwarnlimit
        self.lowerrorlimit = lowerrorlimit
        self.higherrorlimit = higherrorlimit
        self.paniconerror = paniconerror
        super().__init__()
        self._checkLimits()

    def value(self):
        return self._value

    def update(self, newvalue: float):
        logger.debug(f'Updating sensor value to {newvalue} of sensor {self.name}')
        self._value = newvalue
        self.valueChanged.emit(newvalue)
        self._checkLimits()

    def setWarnLimits(self, low: Optional[float] = None, high: Optional[float] = None):
        self.lowwarnlimit = low
        self.highwarnlimit = high
        self._checkLimits()

    def setErrorLimits(self, low: Optional[float] = None, high: Optional[float] = None):
        self.lowerrorlimit = low
        self.higherrorlimit = high
        self._checkLimits()

    def _checkLimits(self) -> bool:
        if np.isnan(self._value):
            if self._errorstate != ErrorState.Unknown:
                self._errorstate = ErrorState.Unknown
                logger.debug(f'Sensor {self.name} just became UNKNOWN.')
                self.unknown.emit()
                return False
        elif (self.lowerrorlimit is not None) and (self._value < self.lowerrorlimit):
            if self._errorstate != ErrorState.Error:
                self._errorstate = ErrorState.Error
                logger.debug(f'Sensor {self.name} just became ERROR.')
                self.error.emit()
                return False
        elif (self.higherrorlimit is not None) and (self._value > self.higherrorlimit):
            if self._errorstate != ErrorState.Error:
                self._errorstate = ErrorState.Error
                logger.debug(f'Sensor {self.name} just became ERROR.')
                self.error.emit()
                return False
        elif (self.lowwarnlimit is not None) and (self._value < self.lowwarnlimit):
            if self._errorstate != ErrorState.Warning:
                self._errorstate = ErrorState.Warning
                logger.debug(f'Sensor {self.name} just became WARNING.')
                self.warning.emit()
                return False
        elif (self.highwarnlimit is not None) and (self._value > self.highwarnlimit):
            if self._errorstate != ErrorState.Warning:
                self._errorstate = ErrorState.Warning
                logger.debug(f'Sensor {self.name} just became WARNING.')
                self.warning.emit()
                return False
        else:
            if self._errorstate != ErrorState.OK:
                self._errorstate = ErrorState.OK
                logger.stronginfo(f'Sensor {self.name} just became OK.')
                self.ok.emit()
                return True
        logger.debug(f'Sensor {self.name} state did not change: currently {self._errorstate}')
        return True

    def isWarning(self) -> bool:
        return self._errorstate == ErrorState.Warning

    def isError(self) -> bool:
        return self._errorstate == ErrorState.Error

    def isOK(self) -> bool:
        return self._errorstate == ErrorState.OK

    def isUnknown(self) -> bool:
        return self._errorstate == ErrorState.Unknown

    def __getstate__(self) -> Dict[str, Any]:
        return {
            'name':self.name,
            'type': self.sensortype,
            'quantity': self.quantityname,
            'device': self.devicename,
            'index':self.index,
            'value': self.value(),
            'units': self.units,
            'warnlimits': (self.lowwarnlimit, self.highwarnlimit),
            'errorlimits': (self.lowerrorlimit, self.higherrorlimit),
            'status': self._errorstate.name,
        }
