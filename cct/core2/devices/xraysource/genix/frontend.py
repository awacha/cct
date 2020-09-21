import logging

from PyQt5 import QtCore

from .backend import GeniXBackend
from ...device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GeniX(DeviceFrontend):
    devicetype = 'source'
    devicename = 'GeniX'
    backendclass = GeniXBackend

    shutter = QtCore.pyqtSignal(bool)

    def moveShutter(self, requestedstate: bool):
        logger.info(f'{"Opening" if requestedstate else "Closing"} shutter')
        if self['shutter'] is requestedstate:
            self.shutter.emit(requestedstate)
        self.issueCommand('shutter', requestedstate)

    def startWarmUp(self):
        self.issueCommand('start_warmup')

    def stopWarmUp(self):
        self.issueCommand('stop_warmup')

    def powerStatus(self) -> str:
        return self['power_status']

    def powerDown(self):
        self.issueCommand('poweroff')

    def standby(self):
        self.issueCommand('standby')

    def rampup(self):
        self.issueCommand('full_power')

    def resetFaults(self):
        self.issueCommand('reset_faults')

    def xraysOff(self):
        self.issueCommand('xrays', False)

    def xraysOn(self):
        self.issueCommand('xrays', True)
