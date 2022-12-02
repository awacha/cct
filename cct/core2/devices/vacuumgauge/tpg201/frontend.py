from typing import Any

import h5py

from .backend import TPG201Backend
from ..generic import VacuumGauge
from ....sensors.manometer import Manometer


class TPG201(VacuumGauge):
    devicename = 'TPG201'
    vendor = 'Thyracont GmbH'
    backendclass = TPG201Backend

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(name, host, port, **kwargs)
        self.sensors = [Manometer('vacuum', self.name, 0, 'mbar', highwarnlimit=1, higherrorlimit=99)]

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename == 'pressure':
            self.sensors[0].update(float(newvalue))

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        grp = super().toNeXus(grp)
        self.create_hdf5_dataset(grp, 'model', self.get('version'))
        self.create_hdf5_dataset(grp, 'short_name', 'TPG201')
        self.create_hdf5_dataset(grp, 'measurement', 'pressure')
        self.create_hdf5_dataset(grp, 'type', 'Pirani')
        self.create_hdf5_dataset(grp, 'run_control', False)
        self.create_hdf5_dataset(grp, 'value', self.get('pressure'), units=self.get('units'))
        return grp