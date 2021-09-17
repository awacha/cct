from typing import Any

from .backend import Keen800Backend
from ..generic import UPS
from ....sensors.thermometer import Thermometer

class Keen800(UPS):
    devicename = 'Keen800'
    backendclass = Keen800Backend

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(name, host, port, **kwargs)
        self.sensors=[Thermometer('ups temperature', self.name, 0, '°C', highwarnlimit=30, higherrorlimit=40)]

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        if variablename == 'utilityfail':
            if newvalue:
                self.utilityPowerFailed.emit()
            else:
                self.utilityPowerRestored.emit()
        elif variablename == 'temperature':
            self.sensors[0].update(newvalue)