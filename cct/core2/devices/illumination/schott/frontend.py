from typing import Any

import h5py

from .backend import SchottKL2500LEDBackend
from ....sensors.thermometer import Thermometer
from ...device.frontend import DeviceFrontend, DeviceType


class KL2500LED(DeviceFrontend):
    devicetype = DeviceType.Illumination
    vendor = 'Schott Ltd.'
    devicename = 'KL2500LED'
    backendclass = SchottKL2500LEDBackend

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(name, host, port, **kwargs)
        self.sensors = [Thermometer('LED PCB temperature', self.name, 0, '°C', highwarnlimit=40, higherrorlimit=60)]

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename == 'temperature':
            self.sensors[0].update(float(newvalue))

    def setBrightness(self, value: int):
        if (value < 0) or (value > self.backendclass.maximumBrightness):
            raise ValueError('Requested brightness out of range.')
        self.issueCommand('set_brightness', value)

    def closeShutter(self):
        self.issueCommand('shutter', True)

    def openShutter(self):
        self.issueCommand('shutter', False)

    def frontPanelLockout(self, lockout: bool):
        self.issueCommand('frontpanellockout', bool(lockout))

    def setFullBrightness(self):
        self.issueCommand('set_full_brightness')

    def setDark(self):
        self.issueCommand('set_brightness', 0)

    @property
    def maximumBrightness(self):
        return self.backendclass.maximumBrightness

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        """"""
        # the NeXus specification does not have a base class for sample illumination sources (as of June 2022)
        return grp
