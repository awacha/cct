from .backend import TPG201Backend
from ..generic import VacuumGauge
from ....sensors.manometer import Manometer


class TPG201(VacuumGauge):
    devicename = 'TPG201'
    backendclass = TPG201Backend

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(name, host, port, **kwargs)
        self.sensors = [Manometer('vacuum', self.name, 0, 'mbar')]
