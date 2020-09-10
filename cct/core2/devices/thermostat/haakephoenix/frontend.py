from .backend import HaakePhoenixBackend
from ...device.frontend import DeviceFrontend

import datetime


class HaakePhoenix(DeviceFrontend):
    backendclass = HaakePhoenixBackend
    devicename = 'HaakePhoenix'
    devicetype = 'thermostat'

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


