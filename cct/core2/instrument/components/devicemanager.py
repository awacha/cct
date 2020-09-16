import logging
from collections import namedtuple
from typing import Dict, List, Any, Type, Iterator

from PyQt5 import QtCore, QtGui

from .auth.privilege import Privilege
from .component import Component
from ...devices.device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DeviceClassDataTuple = namedtuple('DeviceClassDataTuple',
                                  ['deviceclassname', 'devicename', 'host', 'port'])


class DeviceManager(QtCore.QAbstractItemModel, Component):
    devices: Dict[str, DeviceFrontend]
    _deviceclasses: List[DeviceClassDataTuple]
    deviceDisconnected = QtCore.pyqtSignal(str, bool)
    deviceConnected = QtCore.pyqtSignal(str)

    def __init__(self, **kwargs):
        self.devices = {}
        super().__init__(**kwargs)

    def loadFromConfig(self):
        self.beginResetModel()
        self._deviceclasses = []
        if 'connections' in self.config:
            for key, value in self.config['connections'].items():
                logger.debug(f'Loading device info from key {key}')
                self._deviceclasses.append(
                    DeviceClassDataTuple(
                        deviceclassname=value['classname'],
                        devicename=value['name'],
                        host=value['host'],
                        port=value['port']))
        self._deviceclasses = sorted(self._deviceclasses, key=lambda dc: dc.devicename)
        self.endResetModel()

    def saveToConfig(self):
        self.config['connections'] = {dc.devicename: {
            'classname': dc.deviceclassname, 'name': dc.devicename, 'host': dc.host, 'port': dc.port}
            for dc in self._deviceclasses}
        removeddevices = [d for d in self.config['connections'] if
                          d not in {dc.devicename for dc in self._deviceclasses}]
        for dn in removeddevices:
            del self.config['connections'][dn]

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._deviceclasses)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 5

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled

    @staticmethod
    def getDriverClass(deviceclassname: str) -> Type[DeviceFrontend]:
        return [cls for cls in DeviceFrontend.subclasses() if cls.devicename == deviceclassname][0]

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        devclass = self._deviceclasses[index.row()]
        if (role == QtCore.Qt.DisplayRole) and (index.column() == 0):
            return devclass.devicename
        elif (role == QtCore.Qt.DisplayRole) and (index.column() == 1):
            try:
                return self.getDriverClass(devclass.deviceclassname).devicetype
            except IndexError:
                return '-- invalid driver class --'
        elif (role == QtCore.Qt.DisplayRole) and (index.column() == 2):
            return devclass.deviceclassname
        elif (role == QtCore.Qt.DisplayRole) and (index.column() == 3):
            return devclass.host
        elif (role == QtCore.Qt.DisplayRole) and (index.column() == 4):
            return devclass.port
        elif (role == QtCore.Qt.DecorationRole) and (index.column() == 0):
            return QtGui.QIcon.fromTheme('network-idle') \
                if devclass.devicename in self.devices else QtGui.QIcon.fromTheme('network-offline')
        elif role == QtCore.Qt.UserRole:
            return devclass.devicename
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Device name', 'Type', 'Driver', 'Host', 'Port'][section]

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        return False

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def connectDevices(self):
        logger.info('Connecting to devices')
        for dc in self._deviceclasses:
            self.connectDevice(dc.devicename)

    def disconnectDevices(self):
        logger.info('Disconnecting devices')
        self.stopping = True
        if not self.devices:
            QtCore.QTimer.singleShot(100, self.stopped.emit)
            logger.debug('No devices, emitting stopped.')
        for name in self.devices:
            self.disconnectDevice(name)

    def disconnectDevice(self, devicename: str):
        if not self.instrument.auth.hasPrivilege(Privilege.ConnectDevices):
            raise RuntimeError('Insufficient privileges to connect devices')
        self.devices[devicename].stopbackend()

    def connectDevice(self, devicename: str):
        if not self.instrument.auth.hasPrivilege(Privilege.ConnectDevices):
            raise RuntimeError('Insufficient privileges to connect devices')
        if not self.instrument.online:
            raise RuntimeError('Cannot connect devices in offline mode.')
        classinfo = [dc for dc in self._deviceclasses if dc.devicename == devicename][0]
        cls = self.getDriverClass(classinfo.deviceclassname)
        assert issubclass(cls, DeviceFrontend)
        logger.info(f'Connecting to device {devicename}. Driver class is {str(cls)}.')
        device = cls(name=classinfo.devicename, host=classinfo.host, port=classinfo.port)
        device.connectionEnded.connect(self.onConnectionEnded)
        device.panic.connect(self.onPanic)
        device.error.connect(self.onError)
        self.devices[classinfo.devicename] = device
        logger.info(f'Connected to device {device.name}')
        self.deviceConnected.emit(classinfo.devicename)
        row = [i for i, dc in enumerate(self._deviceclasses) if dc.devicename == devicename][0]
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [QtCore.Qt.DecorationRole])

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

    def devicenames(self) -> List[str]:
        return list(self.devices.keys())

    def __iter__(self) -> Iterator[DeviceFrontend]:
        for dev in self.devices.values():
            yield dev

    def __getitem__(self, item: str) -> DeviceFrontend:
        return self.devices[item]

    def detector(self) -> DeviceFrontend:
        return [d for d in self.devices.values() if d.devicetype == 'detector'][0]

    def source(self) -> DeviceFrontend:
        return [d for d in self.devices.values() if d.devicetype == 'source'][0]

    def vacuum(self) -> DeviceFrontend:
        return [d for d in self.devices.values() if d.devicetype == 'vacuumgauge'][0]

    def temperature(self) -> DeviceFrontend:
        return [d for d in self.devices.values() if d.devicetype == 'thermostat'][0]

    def addDevice(self, devicename: str, classname: str, host: str, port: int):
        if not self.instrument.auth.hasPrivilege(Privilege.DeviceConfiguration):
            raise RuntimeError('Cannot add device: insufficient privileges.')
        devclass = DeviceClassDataTuple(classname, devicename, host, port)
        row = max([i for i, dc in enumerate(self._deviceclasses) if dc.devicename < devicename] + [-1]) + 1
        logger.info(f'Adding device class: {devclass}')
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._deviceclasses.insert(row, devclass)
        self.endInsertRows()
        self.saveToConfig()

    def removeDevice(self, devicename: str):
        if not self.instrument.auth.hasPrivilege(Privilege.DeviceConfiguration):
            raise RuntimeError('Cannot remove device: insufficient privileges.')
        if self.isConnected(devicename):
            raise RuntimeError('Cannot remove connected device.')
        row = [i for i, dc in enumerate(self._deviceclasses) if dc.devicename == devicename][0]
        logger.info(f'Removing device class: {self._deviceclasses[row]}')
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._deviceclasses[row]
        self.endRemoveRows()
        self.saveToConfig()

    def isConnected(self, devicename: str) -> bool:
        return devicename in self.devices

    def startComponent(self):
        if self.instrument.online:
            self.connectDevices()
        self.started.emit()

    def stopComponent(self):
        self.stopping = True
        self.disconnectDevices()