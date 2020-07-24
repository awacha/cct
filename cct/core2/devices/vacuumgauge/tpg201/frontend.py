from .backend import TPG201Backend
from ...device.frontend import DeviceFrontend


class TPG201(DeviceFrontend):
    devicetype = 'vacuumgauge'
    devicename = 'TPG201'
    backendclass = TPG201Backend
