from .backend import HaakePhoenixBackend
from ...device.frontend import DeviceFrontend


class HaakePhoenix(DeviceFrontend):
    backendclass = HaakePhoenixBackend
    devicename = 'HaakePhoenix'
    devicetype = 'thermostat'
