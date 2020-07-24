import logging
from typing import Dict

from PyQt5 import QtCore

from .component import Component
from ...devices.device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class DeviceManager(QtCore.QObject, Component):
    devices: Dict[str, DeviceFrontend]
    deviceDisconnected = QtCore.pyqtSignal(str, bool)
    deviceConnected = QtCore.pyqtSignal(str)
    stopping: bool=False
    stopped = QtCore.pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.devices = {}

    def connectDevices(self):
        logger.info('Connecting to devices')
        for key in self.config['connections']:
            self.connectDevice(self.config['connections'][key]['name'])

    def disconnectDevices(self):
        logger.info('Disconnecting devices')
        self.stopping = True
        if not self.devices:
            QtCore.QTimer.singleShot(100, self.stopped.emit)
            logger.debug('No devices, emitting stopped.')
        for name in self.devices:
            self.devices[name].stopbackend()

    def connectDevice(self, devicename: str):
        key = [k for k in self.config['connections'] if self.config['connections'][k]['name'] == devicename][0]
        classname = self.config['connections'][key]['classname']
        logger.debug(f'Trying to find device frontend class for class name {classname}')
        try:
            cls = [sc for sc in DeviceFrontend.subclasses() if sc.devicename == classname][0]
        except IndexError:
            logger.error(f'Could not find device class for name {classname}')
            return
        assert issubclass(cls, DeviceFrontend)
        device = cls(
            self.config['connections'][key]['name'],
            self.config['connections'][key]['host'],
            self.config['connections'][key]['port']
        )
        device.connectionEnded.connect(self.onConnectionEnded)
        device.panic.connect(self.onPanic)
        device.error.connect(self.onError)
        self.devices[self.config['connections'][key]['name']] = device
        logger.info(f'Connected to device {device.name}')
        self.deviceConnected.emit(self.config['connections'][key]['name'])

    def onConnectionEnded(self, expected: bool):
        device = self.sender()
        assert isinstance(device, DeviceFrontend)
        logger.log(logging.INFO if expected else logging.WARNING, f'Disconnected from device {device.name}')
        name = device.name
        was_ready = device.ready
        device.deleteLater()
        self.deviceDisconnected.emit(device.name, expected)
        del self.devices[name]
        if (not expected) and was_ready and (not self.stopping):
            # unexpected disconnection but it was operational before: try to connect again.
            logger.info(f'Reconnecting to device {name}')
            self.connectDevice(name)
        if self.stopping and not self.devices:
            self.stopped.emit()

    def onError(self):
        pass

    def onPanic(self):
        pass

    def __getitem__(self, item: str) -> DeviceFrontend:
        return self.devices[item]

    def detector(self) -> DeviceFrontend:
        return [d for d in self.devices.values() if d.devicetype == 'detector'][0]

    def source(self) -> DeviceFrontend:
        return [d for d in self.devices.values() if d.devicetype == 'source'][0]
