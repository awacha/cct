from .backend import PilatusBackend
from ...device.frontend import DeviceFrontend


class PilatusDetector(DeviceFrontend):
    devicename = 'Pilatus'
    devicetype = 'detector'
    backendclass = PilatusBackend
