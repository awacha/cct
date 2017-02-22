import logging
import weakref

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
from ....core.instrument.instrument import Instrument
from ....core.instrument.privileges import PRIV_LAYMAN
from ....core.devices import Device, Motor
from typing import Union
from PyQt5 import QtCore, QtGui, QtWidgets


class ToolWindow(object):
    def __init__(self, credo, required_devices=[], privilegelevel=PRIV_LAYMAN):
        try:
            self.credo = weakref.proxy(credo)
        except TypeError:
            self.credo = credo
        assert isinstance(self.credo, Instrument)  # this works even if self.credo is a weakproxy to Instrument
        self._device_connections = {}
        self.minimumPrivilegeLevel = privilegelevel
        for d in required_devices:
            self.requireDevice(d)
        self._privlevelconnection = self.credo.services['accounting'].connect('privlevel-changed', self.onPrivLevelChanged)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

    def requireDevice(self, devicename: str):
        assert isinstance(self.credo, Instrument)
        try:
            device = self.credo.get_device(devicename)
        except KeyError:
            # ToDo
            raise
        assert isinstance(device, (Device, Motor))
        self._device_connections[device] = [
            device.connect('variable-change', self.onDeviceVariableChange),
            device.connect('error', self.onDeviceError),
            device.connect('disconnect', self.onDeviceDisconnect),
            device.connect('ready', self.onDeviceReady)
        ]
        if isinstance(device, Motor):
            self._device_connections[device].extend([
                device.connect('position-change', self.onMotorPositionChange),
                device.connect('stop', self.onMotorStop),
            ])

    def onPrivLevelChanged(self, accountingservice, privlevel):
        if privlevel < self.minimumPrivilegeLevel:
            self.cleanup()
            self.close()

    def onDeviceVariableChange(self, device: Union[Device, Motor], variablename: str, newvalue):
        return False

    def onDeviceError(self, device: Union[Device, Motor], variablename: str, exception: Exception,
                      formatted_traceback: str):
        return False

    def onDeviceDisconnect(self, device: Union[Device, Motor], abnormal_disconnection: bool):
        return False

    def onDeviceReady(self, device: Union[Device, Motor]):
        return False

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        return False

    def onMotorStop(self, motor: Motor, targetpositionreached: bool):
        return False

    def unrequireDevice(self, device:Union[str, Device, Motor]):
        if isinstance(device, str):
            device = self.credo.get_device(device)
        try:
            for cid in self._device_connections[device]:
                device.disconnect(cid)
        finally:
            del self._device_connections[device]

    def cleanup(self):
        logger.debug('Cleanup() called on ToolWindow {}'.format(self.objectName()))
        for d in list(self._device_connections.keys()):
            self.unrequireDevice(d)
        if self._privlevelconnection is not None:
            self.credo.services['accounting'].disconnect(self._privlevelconnection)
            self._privlevelconnection=None
        logger.debug('Cleanup() finished on ToolWindow {}'.format(self.objectName()))

    def closeEvent(self, event:QtGui.QCloseEvent):
        logger.debug('CloseEvent received for ToolWindow {}'.format(self.objectName()))
        self.cleanup()
        if isinstance(self, QtWidgets.QDockWidget):
            return QtWidgets.QDockWidget.closeEvent(self, event)
        elif isinstance(self, QtWidgets.QMainWindow):
            return QtWidgets.QMainWindow.closeEvent(self, event)
        else: #isinstance(self, QtWidgets.QWidget)
            return QtWidgets.QWidget.closeEvent(self, event)
