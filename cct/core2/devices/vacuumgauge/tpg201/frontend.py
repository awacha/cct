from typing import Any

from .backend import TPG201Backend
from ..generic import VacuumGauge
from ....sensors.manometer import Manometer


class TPG201(VacuumGauge):
    devicename = 'TPG201'
    backendclass = TPG201Backend

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(name, host, port, **kwargs)
        self.sensors = [Manometer('vacuum', self.name, 0, 'mbar', highwarnlimit=1, higherrorlimit=99)]

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename == 'pressure':
            self.sensors[0].update(float(newvalue))