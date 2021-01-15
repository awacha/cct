import logging
from typing import Any

from PyQt5 import QtCore

from .backend import SE521Backend
from ...device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SE521(DeviceFrontend):
    backendclass = SE521Backend
    devicename = 'SE521'
    devicetype = 'thermometer'
    temperatureChanged = QtCore.pyqtSignal(int, float)

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
