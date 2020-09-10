from .backend import HaakePhoenixBackend
from ...device.frontend import DeviceFrontend


class HaakePhoenix(DeviceFrontend):
    backendclass = HaakePhoenixBackend
    devicename = 'HaakePhoenix'
    devicetype = 'thermostat'

    def temperature(self) -> float:
        return self['temperature']
