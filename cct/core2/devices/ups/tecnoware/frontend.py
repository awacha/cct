from typing import Any

import h5py

from .backend import TecnowareEvoDSPPlusBackend
from ..generic import UPS
from ....sensors.thermometer import Thermometer


class TecnowareEvoDSPPlus(UPS):
    devicename = 'TecnowareEvoDSPPlus'
    vendor = 'Tecnoware'
    backendclass = TecnowareEvoDSPPlusBackend

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(name, host, port, **kwargs)
        self.sensors = [
            Thermometer('ups temperature', self.name, 0, '°C', highwarnlimit=40, higherrorlimit=50, paniconerror=True),
            Thermometer('pfc', self.name, 1, '°C', highwarnlimit=40, higherrorlimit=50, paniconerror=True),
            Thermometer('ambient', self.name, 2, '°C', highwarnlimit=40, higherrorlimit=50, paniconerror=True),
            Thermometer('charger', self.name, 3, '°C', highwarnlimit=40, higherrorlimit=50, paniconerror=True),
        ]

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        if variablename == 'utilityfail':
            if newvalue:
                self.utilityPowerFailed.emit()
            else:
                self.utilityPowerRestored.emit()
        elif variablename == 'temperature':
            self.sensors[0].update(newvalue)
        elif variablename == 'temperature.pfc':
            self.sensors[1].update(newvalue)
        elif variablename == 'temperature.ambient':
            self.sensors[2].update(newvalue)
        elif variablename == 'temperature.charger':
            self.sensors[3].update(newvalue)

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        """"""
        # the NeXus specification does not have a base class for UPS devices (as of June 2022)
        return super().toNeXus(grp)
