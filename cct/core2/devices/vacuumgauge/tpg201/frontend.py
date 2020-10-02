from .backend import TPG201Backend
from ..generic import VacuumGauge


class TPG201(VacuumGauge):
    devicename = 'TPG201'
    backendclass = TPG201Backend