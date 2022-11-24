from typing import Any

from ...device.frontend import DeviceFrontend, DeviceType
from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot


class VacuumGauge(DeviceFrontend):
    devicetype = DeviceType.VacuumGauge
    pressureChanged = Signal(float)

    def pressure(self) -> float:
        return self['pressure']

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename == 'pressure':
            self.pressureChanged.emit(float(newvalue))
