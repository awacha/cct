from typing import Any

from ...device.frontend import DeviceFrontend, DeviceType
from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot


class UPS(DeviceFrontend):
    devicetype = DeviceType.UPS
    utilityPowerFailed = Signal()
    utilityPowerRestored = Signal()

