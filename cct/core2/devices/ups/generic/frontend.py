from typing import Any

from ...device.frontend import DeviceFrontend, DeviceType
from PyQt5 import QtCore


class UPS(DeviceFrontend):
    devicetype = DeviceType.UPS
    utilityPowerFailed = QtCore.pyqtSignal()
    utilityPowerRestored = QtCore.pyqtSignal()

