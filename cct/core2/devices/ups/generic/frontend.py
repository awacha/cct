from ...device.frontend import DeviceFrontend, DeviceType
from PySide6.QtCore import Signal


class UPS(DeviceFrontend):
    devicetype = DeviceType.UPS
    utilityPowerFailed = Signal()
    utilityPowerRestored = Signal()

