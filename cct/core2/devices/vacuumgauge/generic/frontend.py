from typing import Any

from ...device.frontend import DeviceFrontend, DeviceType
from PyQt5 import QtCore


class VacuumGauge(DeviceFrontend):
    devicetype = DeviceType.VacuumGauge
    pressureChanged = QtCore.pyqtSignal(float)

    def pressure(self) -> float:
        return self['pressure']

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename == 'pressure':
            self.pressureChanged.emit(float(newvalue))
