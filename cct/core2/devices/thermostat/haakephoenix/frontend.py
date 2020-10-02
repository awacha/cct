import datetime
from typing import Any

from PyQt5 import QtCore

from .backend import HaakePhoenixBackend
from ...device.frontend import DeviceFrontend


class HaakePhoenix(DeviceFrontend):
    backendclass = HaakePhoenixBackend
    devicename = 'HaakePhoenix'
    devicetype = 'thermostat'
    temperatureChanged = QtCore.pyqtSignal(float)
    startStop = QtCore.pyqtSignal(bool)

    def temperature(self) -> float:
        return self['temperature']

    def highlimit(self) -> float:
        return self['highlimit']

    def lowlimit(self) -> float:
        return self['lowlimit']

    def setpoint(self) -> float:
        return self['setpoint']

    def startCirculator(self):
        self.issueCommand('start')

    def stopCirculator(self):
        self.issueCommand('stop')

    def setSetpoint(self, setpoint: float):
        self.issueCommand('setpoint', setpoint)

    def setLowLimit(self, lowlimit: float):
        self.issueCommand('lowlimit', lowlimit)

    def setHighLimit(self, highlimit: float):
        self.issueCommand('highlimit', highlimit)

    def setDate(self, date: datetime.date):
        self.issueCommand('setdate', date)

    def setTime(self, time: datetime.time):
        self.issueCommand('settime', time)

    def isRunning(self) -> bool:
        return self['__status__'] == HaakePhoenixBackend.Status.Running

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        if variablename == '__status__':
            if newvalue == HaakePhoenixBackend.Status.Running:
                self.startStop.emit(True)
            elif newvalue == HaakePhoenixBackend.Status.Stopped:
                self.startStop.emit(False)
            else:
                pass
        elif variablename == 'temperature':
            self.temperatureChanged.emit(float(newvalue))
