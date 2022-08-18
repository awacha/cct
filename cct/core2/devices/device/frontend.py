import enum
import logging
import queue
from multiprocessing import Queue, Process
from typing import Any, Type, List, Iterator, Dict, Optional, Tuple
import time

import h5py
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from .backend import DeviceBackend
from .message import Message
from .telemetry import TelemetryInformation
from .variable import Variable
from ...algorithms.queuewaiter import QueueWaiter
from ...sensors.sensor import Sensor


class DeviceType(enum.Enum):
    Unknown = 'unknown'
    Source = 'source'
    Detector = 'detector'
    MotorController = 'motorcontroller'
    Thermostat = 'thermostat'
    VacuumGauge = 'vacuumgauge'
    Thermometer = 'thermometer'
    PeristalticPump = 'peristalticpump'
    Illumination = 'illumination'
    UPS = 'ups'


class DeviceConnectionState(enum.Enum):
    Offline = 0
    Initializing = 1
    Online = 2
    Reconnecting = 3


class DeviceFrontend(QtCore.QAbstractItemModel):
    """A base class for devices. This is the front-end part, running in the main process, communicating with the
    backend"""

    # redefine these attributes in subclasses:
    devicetype: DeviceType = DeviceType.Unknown  # source, detector, motorcontroller, thermostat, vacuumgauge etc.
    devicename: str = None  # unique identifier of the device make/model
    vendor: str = 'Unknown'  # device vendor name
    backendclass: Type[DeviceBackend]

    currentMessage: Optional[Message] = None
    sensors: List[Sensor] = None

    connectionstate: DeviceConnectionState=DeviceConnectionState.Offline

    # whenever the connection to the device is broken after a successful initialization, connection is retried.
    connectRetries: List[float] = [0, 1, 2, 5]
    _connectretry: Optional[int] = None

    # do not touch these attributes in subclasses
    _variables: List[Variable] = None
    _backend: Optional[Process] = None
    _queue_from_backend: Queue = None
    _queue_to_backend: Queue = None
    _host: str
    _port: int
    _last_ready_time: Optional[float] = None
    _ready: bool = False

    class PanicState(enum.Enum):
        NoPanic = enum.auto()
        Panicking = enum.auto()
        Panicked = enum.auto()

    _panicking: PanicState = PanicState.NoPanic
    name: str
    _backendkwargs: Dict[str, Any] = None
    _logger: logging.Logger
    _backendlogger: logging.Logger

    loglevel: int = logging.INFO

    # Signals

    # the `variableChanged` signal is emitted whenever a value of a variable changes. Its arguments are the name,
    # new and previous value of the variable.
    variableChanged = Signal(str, object, object)

    # `connectionEnded` is the last signal of a device, meaning that the connection to the hardware device is broken,
    # either intentionally (argument is True) or because of a communication error (argument is False).
    connectionEnded = Signal(bool)

    # `deviceOffline` is emitted if contact is lost with the device. The device is temporarily not functional, until
    # the next `allVariablesReady` signal is received or `connectionEnded` is sent.
    connectionLost = Signal(bool)

    # Emitted when all variables have been successfully queried. The device is considered fully operational only after
    # this signal is emitted.
    allVariablesReady = Signal()

    # Emitted when telemetry (debugging) information received from the backend.
    telemetry = Signal(TelemetryInformation)

    # the panic signal signifies severe hardware error, requiring immediate user response. The device remains
    # operational
    panic = Signal(str)

    # Non-fatal error in the backend.
    error = Signal(str)

    # Command result. Arguments:
    #   - bool: True if success, False if failed
    #   - str: command name
    #   - str: error message if failed, result if successful
    # The backend should reply as soon as it receives the command, must not wait for the operation (e.g. exposure or
    # motor movement) to complete.
    commandResult = Signal(bool, str, str)

    # State change: change in the __status__ variable
    stateChanged = Signal(str)  # the new value

    # Panic acknowledged signal: when a panic situation arises anywhere in the instrument, the panichandler() method
    # of each device is called. The device then needs to stop anything it is doing and shut down into a clean state.
    # When this is achieved, the panicAcknowledged() signal is emitted to notify the instrument.
    panicAcknowledged = Signal()

    class DeviceError(Exception):
        pass

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(None)
        self.sensors = []
        self.name = name
        # initialize variables
        self._variables = []
        self._queue_from_backend = Queue()
        self._queue_to_backend = Queue()
        self._host = host
        self._port = port
        self._logger = logging.getLogger(f'{__name__}:{self.name}')
        self._logger.setLevel(self.loglevel)
        self._backendlogger = logging.getLogger(f'{__name__}:{self.name}:backend')
        self._backendlogger.setLevel(self.loglevel)
        self.connectionstate = DeviceConnectionState.Offline

    def startBackend(self):
        if (self._backend is not None) and (self._backend.is_alive()):
            raise self.DeviceError('Cannot start backend: already running')
        self._ready = False
        self._variables = []
        while True:
            # flush queue
            try:
                self._queue_from_backend.get_nowait()
            except queue.Empty:
                break
        self._backend = Process(target=self.backendclass.create_and_run,
                                args=(self._queue_to_backend, self._queue_from_backend, self._host, self._port),
                                kwargs=self._backendkwargs if self._backendkwargs is not None else {})
        self._backend.start()
        self.connectionstate = DeviceConnectionState.Initializing
        QueueWaiter.instance().registerQueue(self._queue_from_backend, self.onMessageFromBackend)
        # now wait for the variables. The first message from the backend is always 'variablenames', it is sent even
        # before trying to connect to the device itself.
        while True:
            message = self._queue_from_backend.get(True, 5)
            if message.command == 'variablenames':
                self._variables = [
                    Variable(name, querytimeout, vartype) for (name, querytimeout, vartype) in message['names']
                ]
                # self._logger.debug(f'Variables supported by this back-end: {[v.name for v in self._variables]}')
                break
            else:
                raise self.DeviceError(f'The first message from the backend must be a list of variable names. '
                                       f'Instead we got a message of type "{message.command}": {message.kwargs}')

    #        self._logger.debug('Got variable names. Commencing operation.')

    def isOnline(self) -> bool:
        return self.connectionstate == DeviceConnectionState.Online

    def isOffline(self) -> bool:
        return self.connectionstate == DeviceConnectionState.Offline

    def isInitializing(self) -> bool:
        return self.connectionstate == DeviceConnectionState.Initializing

    def onMessageFromBackend(self, message: Message):
        self.currentMessage = message
        try:
            if self.currentMessage.command == 'ready':
                if (not self._ready) and all([v.timestamp is not None for v in self._variables]):
                    self.connectionstate = DeviceConnectionState.Online
                    self._ready = True
                    self._last_ready_time = time.monotonic()
                    self._connectretry = None
                    try:
                        self.allVariablesReady.emit()
                    except Exception as exc:
                        self._logger.critical(
                            f'Exception while emitting the allVariablesReady signal of device {self.name}: {exc}')
                elif not self._ready:
                    raise self.DeviceError('Ready signal got from the backend, but not all variables are initialized!')
                elif self._ready:
                    # happens when self._ready is already set
                    self._logger.warning('Superfluous ready message from the backend.')
            elif self.currentMessage.command == 'variableChanged':
                var = self.getVariable(self.currentMessage['name'])
                var.update(self.currentMessage.kwargs['value'])
                self.onVariableChanged(var.name, var.value, var.previousvalue)
                try:
                    self.variableChanged.emit(var.name, var.value, var.previousvalue)
                except Exception as exc:
                    self._logger.critical(
                        f'Exception while emitting the variableChanged signal of device {self.name}: {exc}')
            elif self.currentMessage.command == 'log':
                self._backendlogger.log(self.currentMessage['level'], self.currentMessage['logmessage'])
            elif self.currentMessage.command == 'telemetry':
                try:
                    # print(self.currentMessage['telemetry'], flush=True)
                    self.telemetry.emit(self.currentMessage['telemetry'])
                except Exception as exc:
                    self._logger.critical(f'Exception while emitting the telemetry signal of device {self.name}: {exc}')
            elif self.currentMessage.command == 'commanderror':
                self.onCommandResult(False, self.currentMessage['commandname'], self.currentMessage['errormessage'])
                try:
                    self.commandResult.emit(False, self.currentMessage['commandname'],
                                            self.currentMessage['errormessage'])
                except Exception as exc:
                    self._logger.critical(
                        f'Exception while emitting the commandResult signal of device {self.name}: {exc}')
                self._logger.error(
                    f'Error while executing command {self.currentMessage["commandname"]} on device {self.name}: {self.currentMessage["errormessage"]}')
            elif self.currentMessage.command == 'commandfinished':
                self.onCommandResult(True, self.currentMessage['commandname'], self.currentMessage['result'])
                try:
                    self.commandResult.emit(True, self.currentMessage['commandname'], self.currentMessage['result'])
                except Exception as exc:
                    self._logger.critical(
                        f'Exception while emitting the commandResult signal of device {self.name}: {exc}')
                # self._logger.debug(f'Command {self.currentMessage["commandname"]} finished successfully on device {self.name}. Result: {self.currentMessage["result"]}')
            elif self.currentMessage.command == 'end':
                self._backend.join()
                # Do not set self._backend to None: we will probably try to restart. Setting it to None means that the
                # device is inactive.
                QueueWaiter.instance().deregisterQueue(self._queue_from_backend)
                if self.currentMessage['expected']:
                    # expected end, requested by the front-end.
                    self._backend = None  # we won't reconnect
                    self.connectionstate = DeviceConnectionState.Offline
                    try:
                        self.connectionLost.emit(True)
                    except Exception as exc:
                        self._logger.critical(
                            f'Exception while emitting the connectionLost signal of device {self.name}: {exc}'
                        )
                    try:
                        self.connectionEnded.emit(True)
                    except Exception as exc:
                        self._logger.critical(
                            f'Exception while emitting the connectionEnded signal of device {self.name}: {exc}'
                        )
                else:
                    # connection to device unexpectedly lost
                    self.connectionstate = DeviceConnectionState.Reconnecting
                    try:
                        self.connectionLost.emit(False)
                    except Exception as exc:
                        self._logger.critical(
                            f'Exception while emitting the connectionLost signal of device {self.name}: {exc}')
                    self.restartBackend()
            elif self.currentMessage.command == 'panicacknowledged':
                self._panicking = self.PanicState.Panicked
                self.panicAcknowledged.emit()
            elif self.currentMessage.command == 'panic':
                self.panic.emit(self.currentMessage['reason'])
        finally:
            self.currentMessage = None

    def restartBackend(self):
        """Try to restart the backend."""
        # this function is called whenever the backend process dies unexpectedly, e.g. due to a communication error.
        # If the communication error is sporadic, the connection can be recovered. Let us retry.

        if self._last_ready_time is None:
            # it was never successfully initialized, give up trying.
            self._logger.warning('Giving up trying to restart backend: it was never successfully initialized.')
            self._backend = None  # we won't retry.
            self.connectionstate = DeviceConnectionState.Offline
            try:
                self.connectionEnded.emit(False)
            except Exception as exc:
                self._logger.critical(
                    f'Exception while emitting the connectionEnded signal of device {self.name}: {exc}'
                )
            return
        elif self._connectretry is None:
            # this is our very first retry.
            self._connectretry = 0
        elif self._connectretry == len(self.connectRetries)-1:
            # this was our last connect retry
            self._logger.error('Giving up trying to restart backend: maximum number of retries exhausted.')
            self._backend = None  # we won't retry
            self.connectionstate = DeviceConnectionState.Offline
            try:
                self.connectionEnded.emit(False)
            except Exception as exc:
                self._logger.critical(
                    f'Exception while emitting the connectionEnded signal of device {self.name}: {exc}'
                )
            return
        else:
            self._connectretry += 1
        self.connectionstate = DeviceConnectionState.Reconnecting
        self._logger.info(f'Trying to reconnect to device in {self.connectRetries[self._connectretry]:.2f} seconds. '
                          f'This retry #{self._connectretry+1} of {len(self.connectRetries)}')
        QtCore.QTimer.singleShot(
            int(self.connectRetries[self._connectretry]*1000), QtCore.Qt.PreciseTimer, self.startBackend)

    @property
    def ready(self) -> bool:
        """Check if all variables have been updated since the start of the device handler"""
        return (self._variables is not None) and all([v.timestamp is not None for v in self._variables]) and \
               (self.connectionstate == DeviceConnectionState.Online)

    def __getitem__(self, item: str) -> Any:
        """Get the value of a variable.

        :param item: variable name
        :type item: str
        :return: the value of the variable
        :rtype: any
        :raises DeviceError: if the variable has not been updated yet
        :raises KeyError: if the variable does not exist.
        """
        try:
            var = [v for v in self._variables if v.name == item][0]
        except IndexError:
            raise KeyError(item)
        if var.timestamp is None:
            #            self._logger.debug('Available variables: \n'+'\n'.join(sorted([f'    {v.name}' for v in self._variables if v.timestamp is not None])))
            #            self._logger.debug('Not available variables: \n'+'\n'.join(sorted([f'    {v.name}' for v in self._variables if v.timestamp is None])))
            raise self.DeviceError(f'Variable {var.name} of device {self.name} has not been updated yet.')
        try:
            return [v.value for v in self._variables if v.name == item][0]
        except IndexError:
            raise KeyError(item)

    def issueCommand(self, command: str, *args):
        """Issue a command to the device.

        Commands are operations which change the internal state of the device, e.g. setting the temperature set-point
        of a thermostat or moving a motor.

        Actual subclasses should implement dedicated methods for each command, calling this method with the appropriate
        command name and arguments.

        :param command: name of the command
        :type command: str
        :param args: arguments required for the command.
        :type args: various
        """
        # self._logger.debug(f'Issuing command: {command} with arguments {args}')
        self._queue_to_backend.put(Message('issuecommand', name=command, args=args))

    def stopbackend(self):
        """Ask the backend process to quit."""
        # self._logger.debug(f'Stopping the back-end process')
        self._queue_to_backend.put(Message('end'))

    def sendpanictobackend(self):
        """Notify the backend of a panic situation, ask it to turn the device off"""
        self._queue_to_backend.put(Message('panic'))

    def keys(self) -> Iterator[str]:
        """Return the names of the variables in an iterator"""
        for v in self._variables:
            yield v.name

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        """This method is called before the variableChanged signal is emitted."""
        row = [i for i, v in enumerate(self._variables) if v.name == variablename][0]
        self.dataChanged.emit(
            self.index(row, 0, QtCore.QModelIndex()),
            self.index(row, self.columnCount(), QtCore.QModelIndex()),
        )
        if variablename == '__status__':
            self.stateChanged.emit(newvalue)

    @classmethod
    def subclasses(cls) -> Iterator[Type["DeviceFrontend"]]:
        """Iterate over all subclasses, recursively"""
        for subclass in cls.__subclasses__():
            assert issubclass(subclass, cls)
            yield subclass
            for sc in subclass.subclasses():
                yield sc

    def getVariable(self, name: str) -> Variable:
        """Get a variable instance. Use this if you want more information than just its value.

        :param name: variable name
        :type name: str
        :return: the variable instance
        :rtype: Variable
        :raises IndexError: if the variable does not exist
        """
        return [v for v in self._variables if v.name == name][0]

    def onCommandResult(self, success: bool, commandname: str, result: str):
        pass

    def toDict(self) -> Dict[str, Any]:
        return {v.name: v.value for v in self._variables}

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 2

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._variables) if self._variables is not None else 0

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Name', 'Value'][section]

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        variable = self._variables[index.row()]
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return variable.name
            elif index.column() == 1:
                return str(variable.value)
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    def panichandler(self):
        """This method is called when there is a "panic" situation from anywhere in the instrument.
        The device needs to clean up and shut down. After the shutdown sequence is completed, the panicAcknowledged()
        signal must be emitted.

        The default handler notifies the backend on the panic situation, which should take the appropriate actions (e.g.
        turning off the X-ray generator or stopping moving motors). If all needed actions have been done, the backend
        replies to the frontend with a 'panicacknowledged' message, resulting in the emission of the panicAcknowledged
        signal.
        """
        self._panicking = self.PanicState.Panicking
        if self.isOffline():
            self._panicking = self.PanicState.Panicked
            QtCore.QTimer.singleShot(1, QtCore.Qt.VeryCoarseTimer, self.panicAcknowledged)
        else:
            self._queue_to_backend.put(Message('panic'))

    def panicking(self) -> PanicState:
        return self._panicking

    def __len__(self) -> int:
        return len(self._variables)

    def __contains__(self, item: str) -> bool:
        return bool([v for v in self._variables if (v.name == item) and v.hasValidValue()])

    def __iter__(self) -> Iterator[Tuple[str, Any]]:
        for v in self._variables:
            yield v.name, v.value

    @staticmethod
    def create_hdf5_dataset(grp: h5py.Group, name: str, data: Any, **kwargs) -> h5py.Dataset:
        ds = grp.create_dataset(name, data=data)
        ds.attrs.update(kwargs)
        return ds

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        """Write the corresponding entry to a HDF5 group conforming to the NeXus format.

        The default implementation creates two NXcollections:
        - statevariables: listing of the state variables
        - devicesensors: sensors

        Note that device-sensors in CCT and NXsensors are totally different concepts. In NeXus, a sensor is a
        stand-alone device (e.g. vacuum gauge, temperature sensor etc), while in CCT it is only a state parameter
        with defined warning and error intervals around it, for monitoring critical state variables.

        Therefore, CCT device-sensors are written in a NXcollection group and not as NXsensor classes.

        Subclasses should additionally set the correct NeXus base class (e.g. NXsource, NXdetector etc.), and create the
        appropriate attributes.

        :param grp: HDF5 group, should be empty
        :type grp: h5py.Group entry
        """
        grp.attrs['NX_class'] = 'NXcollection'  # add a default NX_class, the actual implementation will correct it.
        stategrp = grp.create_group('statevariables')
        stategrp.attrs['NX_class'] = 'NXcollection'
        for variable, value in self:
            stategrp.create_dataset(variable, data=value)
        sensorgrp = grp.create_group('devicesensors')
        sensorgrp.attrs['NX_class'] = 'NXcollection'
        for isensor, sensor in enumerate(self.sensors, start=1):
            sg = sensorgrp.create_group(sensor.name)
            self.create_hdf5_dataset(sg, 'sensortype', sensor.sensortype)
            self.create_hdf5_dataset(sg, 'quantity', sensor.quantityname)
            self.create_hdf5_dataset(sg, 'devicename', sensor.devicename)
            self.create_hdf5_dataset(sg, 'index', sensor.index)
            self.create_hdf5_dataset(sg, 'value', sensor.value(), units=sensor.units)
            self.create_hdf5_dataset(sg, 'lowwarnlimit', sensor.lowwarnlimit, units=sensor.units)
            self.create_hdf5_dataset(sg, 'highwarnlimit', sensor.highwarnlimit, units=sensor.units)
            self.create_hdf5_dataset(sg, 'lowerrorlimit', sensor.lowerrorlimit, units=sensor.units)
            self.create_hdf5_dataset(sg, 'higherrorlimit', sensor.higherrorlimit, uints=sensor.units)
            self.create_hdf5_dataset(sg, 'state', sensor.errorstate().name)
        return grp

