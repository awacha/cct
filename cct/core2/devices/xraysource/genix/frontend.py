import logging
from typing import Any

from PyQt5 import QtCore

from .backend import GeniXBackend
from ...device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GeniX(DeviceFrontend):
    Status = GeniXBackend.Status
    devicetype = 'source'
    devicename = 'GeniX'
    backendclass = GeniXBackend

    shutter = QtCore.pyqtSignal(bool)
    powerStateChanged = QtCore.pyqtSignal(str)

    def moveShutter(self, requestedstate: bool):
        logger.info(f'{"Opening" if requestedstate else "Closing"} shutter')
        if self['shutter'] is requestedstate:
            self.shutter.emit(requestedstate)
        self.issueCommand('shutter', requestedstate)

    def startWarmUp(self):
        if self['__status__'] != GeniXBackend.Status.off:
            raise self.DeviceError('Cannot start warm up sequence: not in off mode.')
        self.issueCommand('start_warmup')

    def stopWarmUp(self):
        if self['__status__'] != GeniXBackend.Status.warmup:
            raise self.DeviceError('Cannot stop warm up sequence: not running.')
        self.issueCommand('stop_warmup')

    def powerStatus(self) -> str:
        return self['__status__']

    def powerDown(self):
        self.issueCommand('poweroff')

    def standby(self):
        if self['__status__'] in [GeniXBackend.Status.off, GeniXBackend.Status.full, GeniXBackend.Status.unknown, GeniXBackend.Status.standby]:
            self.issueCommand('standby')
        else:
            raise self.DeviceError(f'Cannot set X-ray source to standby mode from mode {self["__status__"]}')

    def rampup(self):
        if self['__status__'] != GeniXBackend.Status.standby:
            raise self.DeviceError(f'Cannot put X-ray source to full power mode from mode {self["__status__"]}')
        self.issueCommand('full_power')

    def resetFaults(self):
        self.issueCommand('reset_faults')

    def xraysOff(self):
        if (self['ht'] > 0) or (self['current'] > 0):
            raise self.DeviceError(f'Cannot turn X-rays off before high voltage and current have been set to zero.')
        self.issueCommand('xrays', False)

    def xraysOn(self):
        self.issueCommand('xrays', True)

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename == '__status__':
            if (newvalue == GeniXBackend.Status.off) and (previousvalue == GeniXBackend.Status.warmup):
                logger.debug('Warm-up finished. Going to standby mode.')
                self.standby()
            self.powerStateChanged.emit(newvalue)
        elif variablename == 'shutter':
            logger.info(f'Shutter is now {"open" if newvalue else "closed"}.')
            self.shutter.emit(bool(newvalue))

    def onCommandResult(self, success: bool, commandname: str, result: str):
        super().onCommandResult(success, commandname, result)
        if commandname == 'shutter' and not success:
            logger.error(f'Cannot {"close" if self["shutter"] else "open"} shutter')
            self.shutter.emit(self['shutter'])
