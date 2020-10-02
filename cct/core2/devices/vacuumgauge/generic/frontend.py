from typing import Any

from ...device.frontend import DeviceFrontend
from PyQt5 import QtCore


class VacuumGauge(DeviceFrontend):
    devicetype = 'vacuumgauge'
    pressureChanged = QtCore.pyqtSignal(float)

    def pressure(self) -> float:
        return self['pressure']

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        if variablename == 'pressure':
            self.pressureChanged.emit(float(newvalue))
