import logging
from typing import List, Any, Type, Iterator

from PyQt5 import QtCore

from .auth import Privilege, needsprivilege
from .component import Component
from ...devices.device.frontend import DeviceFrontend
from ...devices.motor.generic.frontend import MotorController
from ....utils import getIconFromTheme

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class DeviceManager(QtCore.QAbstractItemModel, Component):
    """Manage devices

    This component of the Instrument maintains a collection of device frontend objects and makes them available for
    other parts of the code.

    Device frontends are stored by name in the `_devices` member, a list. Device instances are alive from when they are
    `add`ed until they are `remove`d, either automatically at the start or the end of the program, respectively, or by
    the user when defining or removing a device from the UI.

    Devices can be online and offline.


    """
    _devices: List[DeviceFrontend]
    deviceAdded = QtCore.pyqtSignal(str)
    deviceRemoved = QtCore.pyqtSignal(str, bool)

    def __init__(self, **kwargs):
        self._devices = []
        super().__init__(**kwargs)

    def loadFromConfig(self):
        self.beginResetModel()
        self._devices = []
        self.endResetModel()
        if 'connections' in self.config:
            for key, value in self.config['connections'].asdict().items():
                logger.debug(f'Loading device info from key {key}')
                try:
                    self.addDevice(value['name'], value['classname'], value['host'], value['port'])
                except Exception as exc:
                    logger.critical(f'Cannot add device {value["name"]}: {exc}')

    def saveToConfig(self):
        self.config['connections'] = {dev.name: {
            'classname': dev.__class__.devicename, 'name': dev.name, 'host': dev.host, 'port': dev.port}
            for dev in self._devices}
        removeddevices = [d for d in self.config['connections'] if
                          d not in {dev.name for dev in self._devices}]
        for dn in removeddevices:
            del self.config['connections'][dn]
        logger.debug(f'Config connections keys: {list(self.config["connections"].keys())}')

    @staticmethod
    def getDriverClass(deviceclassname: str) -> Type[DeviceFrontend]:
        try:
            return [cls for cls in DeviceFrontend.subclasses() if cls.devicename == deviceclassname][0]
        except IndexError:
            raise ValueError(f'Unknown device class {deviceclassname}')

    def connectDevices(self):
        logger.info('Connecting all devices')
        for dev in self._devices:
            self.connectDevice(dev.name)

    def disconnectDevices(self):
        logger.info('Disconnecting all devices')
        if not self._devices:
            QtCore.QTimer.singleShot(0, QtCore.Qt.VeryCoarseTimer, self.stopped.emit)
            logger.debug('No devices, emitting stopped.')
        for dev in self._devices:
            self.disconnectDevice(dev.name)

    def disconnectDevice(self, devicename: str):
        if self[devicename].isOffline():
            # already off-line, no need to disconnect
            return
        if not (self[devicename].isOnline() or self[devicename].isInitializing()):
            raise ValueError('Cannot disconnect from device: it is not online and not initializing')
        self[devicename].stopbackend()

    def connectDevice(self, devicename: str):
        """Start the backend of an existing device"""
        if not self.instrument.online:
            raise RuntimeError('Cannot connect devices in offline mode.')
        dev = self[devicename]
        if dev.isOnline() or dev.isInitializing():
            # no need to connect, already online
            return
        row = self._devices.index(dev)
        if not dev.isOffline():
            raise RuntimeError(f'Cannot start device backend for device {dev.name}: device is not offline!')
        dev.startBackend()
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [QtCore.Qt.DecorationRole])

    def onConnectionEnded(self, expected: bool):
        device = self.sender()
        assert isinstance(device, DeviceFrontend)
        logger.log(logging.INFO if expected else logging.WARNING, f'Disconnected from device {device.name}')
        if self.stopping and not self._devices:
            self.stopped.emit()

    def onConnectionLost(self):
        # do nothing, this is handled directly by those code pieces which depend on the devices
        pass

    def onError(self):
        pass

    def onPanic(self, reason: str):
        device:DeviceFrontend = self.sender()
        logger.error(f'Device {device.name} panicked! Reason: {reason}. Escalating...')
        self.instrument.panic(reason)

    # ------------------ Convenience methods for accessing devices ---------------------------------------------------------

    def devicenames(self) -> List[str]:
        return [dev.name for dev in self._devices]

    def __iter__(self) -> Iterator[DeviceFrontend]:
        yield from self._devices

    def __contains__(self, item: str) -> bool:
        return item in [dev.name for dev in self._devices]

    def __getitem__(self, item: str) -> DeviceFrontend:
        try:
            return [dev for dev in self._devices if dev.name == item][0]
        except IndexError:
            raise KeyError(item)

    def detector(self) -> DeviceFrontend:
        """Get the first available detector"""
        return [d for d in self._devices if d.devicetype == 'detector'][0]

    def source(self) -> DeviceFrontend:
        """Get the first available X-ray source"""
        return [d for d in self._devices if d.devicetype == 'source'][0]

    def vacuum(self) -> DeviceFrontend:
        """Get the first available vacuum gauge"""
        return [d for d in self._devices if d.devicetype == 'vacuumgauge'][0]

    def temperature(self) -> DeviceFrontend:
        """Get the first available thermostat"""
        return [d for d in self._devices if d.devicetype == 'thermostat'][0]

    def motorcontrollers(self) -> List[MotorController]:
        """Get all motor controllers"""
        return [d for d in self._devices if d.devicetype == 'motorcontroller']

    def peristalticpump(self) -> DeviceFrontend:
        """Get the first available peristaltic pump"""
        return [d for d in self._devices if d.devicetype == 'peristalticpump'][0]

    def ups(self) -> DeviceFrontend:
        """Get the first available ups"""
        return [d for d in self._devices if d.devicetype == 'ups'][0]

    def devicesOfType(self, devicetype: str, online: bool = True) -> List[DeviceFrontend]:
        return [d for d in self._devices if (d.devicetype == devicetype) and (online or d.isOnline())]

    # ----------------------------- Adding and removing devices ------------------------------------------------------------

    @needsprivilege(Privilege.DeviceConfiguration)
    def addDevice(self, devicename: str, classname: str, host: str, port: int):
        """Add a new device to the list

        :param str devicename: the (unique) name of the device
        :param str classname: the name of the device frontend class
        :param str host: host name of the device
        :param int port: TCP port number
        """
        if devicename in self:
            raise RuntimeError(f'Cannot add device: another device with name {devicename} already exists.')
        cls = self.getDriverClass(classname)
        logger.info(f'Adding device: {devicename} of type {classname} at address {host}:{port}')
        self.beginInsertRows(QtCore.QModelIndex(), len(self._devices), len(self._devices))
        dev = cls(devicename, host, port)
        dev.allVariablesReady.connect(self.onDeviceConnectionStatusChanged)
        dev.connectionEnded.connect(self.onConnectionEnded)
        dev.connectionLost.connect(self.onConnectionLost)
        dev.panic.connect(self.onPanic)
        dev.error.connect(self.onError)
        self._devices.append(dev)
        self.endInsertRows()
        self.saveToConfig()
        try:
            self.deviceAdded.emit(devicename)
        except Exception as exc:
            logger.critical(f'Exception while emitting deviceAdded signal for device {devicename}: {exc}')

    @needsprivilege(Privilege.DeviceConfiguration)
    def removeDevice(self, devicename: str):
        try:
            device = self[devicename]
        except KeyError:
            raise ValueError(f'No device with name {devicename}')
        if not device.isOffline():
            raise RuntimeError('Cannot remove connected device.')
        device.allVariablesReady.disconnect(self.onDeviceConnectionStatusChanged)
        device.connectionEnded.disconnect(self.onConnectionEnded)
        device.connectionLost.disconnect(self.onConnectionLost)
        device.panic.disconnect(self.onPanic)
        device.error.disconnect(self.onError)
        row = self._devices.index(device)
        logger.info(f'Removing device {device.name}')
        try:
            self.deviceRemoved.emit(devicename, True)
        except Exception as exc:
            logger.critical(f'Exception while emitting deviceRemoved signal for device {devicename}: {exc}')
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._devices[row]
        self.endRemoveRows()
        self.saveToConfig()

    def onDeviceConnectionStatusChanged(self):
        device = self.sender()
        try:
            row = self._devices.index(device)
        except ValueError:
            logger.warning(f'Got connection status change from an unmanaged device {device.name}')
            return
        self.dataChanged.emit(
            self.index(row, 0, QtCore.QModelIndex()),
            self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def isConnected(self, devicename: str) -> bool:
        return self[devicename].isOnline()

    def startComponent(self):
        if self.instrument.online:
            self.connectDevices()
        self.started.emit()

    def stopComponent(self):
        self.stopping = True
        self.disconnectDevices()

    # ------------ Qt Item Model methods -------------------------------------------------------------------------------

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._devices)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 5

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        dev = self._devices[index.row()]
        if (role == QtCore.Qt.DisplayRole) and (index.column() == 0):
            return dev.name
        elif (role == QtCore.Qt.DisplayRole) and (index.column() == 1):
            try:
                return dev.devicetype
            except IndexError:
                return '-- invalid driver class --'
        elif (role == QtCore.Qt.DisplayRole) and (index.column() == 2):
            return dev.__class__.__name__
        elif (role == QtCore.Qt.DisplayRole) and (index.column() == 3):
            return dev.host
        elif (role == QtCore.Qt.DisplayRole) and (index.column() == 4):
            return dev.port
        elif (role == QtCore.Qt.DecorationRole) and (index.column() == 0):
            if dev.isOffline():
                return getIconFromTheme('network-offline', 'network-wired-offline', 'network-wired-disconnected')
            elif dev.isOnline():
                return getIconFromTheme('network-idle', 'network-wired-activated')
            elif dev.isInitializing():
                return getIconFromTheme('network-transmit-receive', 'network-limited')
            else:
                return getIconFromTheme('network-error', 'network-wired-unavailable')
        elif role == QtCore.Qt.UserRole:
            return dev.name
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Device name', 'Type', 'Driver', 'Host', 'Port'][section]

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        return False

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def onDevicePanicAcknowledged(self):
        device: DeviceFrontend = self.sender()
        logger.info(f'Panic acknowledged by device {device.name}')
        device.panicAcknowledged.disconnect(self.onDevicePanicAcknowledged)
        logger.debug(f'Waiting for devices: {", ".join([dev.name for dev in self._devices if dev.panicking() != dev.PanicState.Panicked])}')
        if all([dev.panicking() == dev.PanicState.Panicked for dev in self._devices]):
            # all devices have reacted
            logger.info('All devices acknowledged the panic situation.')
            self._panicking = self.PanicState.Panicked
            self.panicAcknowledged.emit()

    def panichandler(self):
        self._panicking = self.PanicState.Panicking
        if not [d for d in self._devices if d.isOnline()]:
            super().panichandler()
        else:
            for dev in self._devices:
                dev.panicAcknowledged.connect(self.onDevicePanicAcknowledged)
                logger.info(f'Notifying device {dev.name} on the panic situation')
                dev.panichandler()
