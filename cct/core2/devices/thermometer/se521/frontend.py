import logging
from typing import Any

from PyQt5 import QtCore

from .backend import SE521Backend
from ...device.frontend import DeviceFrontend
from ....sensors.thermometer import Thermometer

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SE521(DeviceFrontend):
    backendclass = SE521Backend
    devicename = 'SE521'
    devicetype = 'thermometer'
    temperatureChanged = QtCore.pyqtSignal(int, float)

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(name, host, port, **kwargs)
        self.sensors = [Thermometer(f't{i}', self.name, i-1, '°C') for i in range(1, 5)]

    def temperature(self, index: int) -> float:
        return self[f't{index}']

    def toggleBacklight(self):
        self.issueCommand('togglebacklight')

    def setDisplayUnits(self):
        self.issueCommand('changeunits')

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename in ['t1', 't2', 't3', 't4']:
            self.temperatureChanged.emit(int(variablename[1]), float(newvalue))
            self.sensors[int(variablename[1])-1].update(float(newvalue))