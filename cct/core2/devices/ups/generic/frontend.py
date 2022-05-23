from typing import Any

from ...device.frontend import DeviceFrontend, DeviceType
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot


class UPS(DeviceFrontend):
    devicetype = DeviceType.UPS
    utilityPowerFailed = Signal()
    utilityPowerRestored = Signal()

