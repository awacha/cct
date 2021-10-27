from typing import Any

from ...device.frontend import DeviceFrontend
from PyQt5 import QtCore


class UPS(DeviceFrontend):
    devicetype = 'ups'
    utilityPowerFailed = QtCore.pyqtSignal()
    utilityPowerRestored = QtCore.pyqtSignal()

