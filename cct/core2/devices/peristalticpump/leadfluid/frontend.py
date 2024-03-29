import enum
import logging
from typing import Any

import h5py

from .backend import BT100SBackend
from ...device.frontend import DeviceFrontend, DeviceType

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ControlMode(enum.Enum):
    Internal = 'internal'
    External = 'external'
    Foot_Switch = 'footswitch'
    Logic_Level = 'logic level'
    Logic_Level_2 = 'logic level 2'


class BT100S(DeviceFrontend):
    Status = BT100SBackend.Status
    devicetype = DeviceType.PeristalticPump
    devicename = 'BT100S'
    backendclass = BT100SBackend
    vendor = 'LeadFluid Ltd.'

    def setRotationSpeed(self, speed: float):
        self.issueCommand('setspeed', speed)

    def setClockwise(self, clockwise: bool):
        self.issueCommand('clockwise' if clockwise else 'counterclockwise')

    def setCounterClockwise(self, counterclockwise: bool):
        self.setClockwise(not counterclockwise)

    def startRotation(self):
        self.issueCommand('start')

    def stopRotation(self):
        self.issueCommand('stop')

    def setFullSpeed(self, fullspeed: bool):
        self.issueCommand('fullspeed' if fullspeed else 'normalspeed')

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)

    def onCommandResult(self, success: bool, commandname: str, result: str):
        super().onCommandResult(success, commandname, result)

    def setControlMode(self, mode: ControlMode):
        self.issueCommand(f'{mode.value.replace(" ", "_")}_control')

    def setEasyDispenseMode(self, active: bool):
        self.issueCommand('set_easy_dispense_mode', active)

    def setTimeDispenseMode(self, active: bool):
        self.issueCommand('set_time_dispense_mode', active)

    def setDispenseVolume(self, microsteps: int):
        self.issueCommand('set_easy_dispense_volume', microsteps)

    def setDispenseTime(self, dispensetime: float):
        self.issueCommand('set_dispense_time', dispensetime)

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        """"""
        # the NeXus specification does not have a base class for peristaltic pumps (as of June 2022)
        return grp
