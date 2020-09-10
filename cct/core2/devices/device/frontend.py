import logging
import queue
from multiprocessing import Queue, Process
from typing import Any, Type, List, Iterator, Dict, Optional

from PyQt5 import QtCore

from .backend import DeviceBackend
from .message import Message
from .telemetry import TelemetryInformation
from .variable import Variable


class DeviceFrontend(QtCore.QAbstractItemModel):
    """A base class for devices. This is the front-end part, running in the main process, communicating with the
    backend"""

    # redefine these attributes in subclasses:
    devicetype: str = 'unknown'  # source, detector, motorcontroller, thermostat, vacuumgauge etc.
    devicename: str  # unique identifier of the device make/model
    backendclass: Type[DeviceBackend]

    currentMessage: Optional[Message] = None

    # do not touch these attributes in subclasses
    _variables: List[Variable] = None
    _backend: Process = None
    _queue_from_backend: Queue = None
    _queue_to_backend: Queue = None
    _host: str
    _port: int
    _timerid: int
    _ready: bool = False
    name: str
    _backendkwargs: Dict[str, Any] = None
    _logger: logging.Logger
    _backendlogger: logging.Logger

    # Signals

    # the `variableChanged` signal is emitted whenever a value of a variable changes. Its arguments are the name,
    # new and previous value of the variable.
    variableChanged = QtCore.pyqtSignal(str, object, object)

    # `connectionEnded` is the last signal of a device, meaning that the connection to the hardware device is broken,
    # either intentionally (argument is True) or because of a communication error (argument is False).
    connectionEnded = QtCore.pyqtSignal(bool)

    # Emitted when all variables have been successfully queried. The device is considered fully operational only after
    # this signal is emitted.
    allVariablesReady = QtCore.pyqtSignal()

    # Emitted when telemetry (debugging) information received from the backend.
    telemetry = QtCore.pyqtSignal(TelemetryInformation)

    # the panic signal signifies severe hardware error, requiring immediate user response. The device remains
    # operational
    panic = QtCore.pyqtSignal(str)

    # Non-fatal error in the backend.
    error = QtCore.pyqtSignal(str)

    # Command result. Arguments:
    #   - bool: True if success, False if failed
    #   - str: command name
    #   - str: error message if failed, result if successful
    # The backend should reply as soon as it receives the command, must not wait for the operation (e.g. exposure or
    # motor movement) to complete.
    commandResult = QtCore.pyqtSignal(bool, str, str)

    class DeviceError(Exception):
        pass

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(None)
        self.name = name
        # initialize variables
        self._variables = []
        self._queue_from_backend = Queue()
        self._queue_to_backend = Queue()
        self._host = host
        self._port = port
        self._backend = Process(target=self.backendclass.create_and_run,
                                args=(self._queue_to_backend, self._queue_from_backend, host, port),
                                kwargs=self._backendkwargs if self._backendkwargs is not None else {})
        self._timerid = self.startTimer(0)
        self._backend.start()
        self._logger = logging.getLogger(f'{__name__}:{self.name}')
        self._backendlogger = logging.getLogger(f'{__name__}:{self.name}:backend')
        self._backendlogger.setLevel(logging.DEBUG)
#        self._logger.debug('Started backend process. Waiting for variable list...')
        # now wait for the variables:
        while True:
            message = self._queue_from_backend.get(True, 5)
            if message.command != 'variablenames':
                continue
            self._variables = [Variable(name, querytimeout) for (name, querytimeout) in message['names']]
#            self._logger.debug(f'Variables supported by this back-end: {[v.name for v in self._variables]}')
            break
#        self._logger.debug('Got variable names. Commencing operation.')

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        """timer event handler

        The main function of this method is to maintain communication with the backend by periodically checking the
        response queue and emitting appropriate signals.

        Signal emissions are protected: if a slot raises an exception, the exception is caught and transformed into a
        log message with 'critical' level.

        """
        try:
            self.currentMessage = self._queue_from_backend.get_nowait()
        except queue.Empty:
            return
        try:
            if self.currentMessage.command == 'variableChanged':
                var = self.getVariable(self.currentMessage['name'])
                var.update(self.currentMessage.kwargs['value'])
                self.onVariableChanged(var.name, var.value, var.previousvalue)
                try:
                    self.variableChanged.emit(var.name, var.value, var.previousvalue)
                except Exception as exc:
                    self._logger.critical(
                        f'Exception while emitting the variableChanged signal of device {self.name}: {exc}')
                if (not self._ready) and all([v.timestamp is not None for v in self._variables]):
                    self._ready = True
                    try:
                        self.allVariablesReady.emit()
                    except Exception as exc:
                        self._logger.critical(
                            f'Exception while emitting the allVariablesReady signal of device {self.name}: {exc}')
            elif self.currentMessage.command == 'log':
                self._backendlogger.log(self.currentMessage['level'], self.currentMessage['logmessage'])
            elif self.currentMessage.command == 'telemetry':
                try:
                    #print(self.currentMessage['telemetry'], flush=True)
                    self.telemetry.emit(self.currentMessage['telemetry'])
                except Exception as exc:
                    self._logger.critical(f'Exception while emitting the telemetry signal of device {self.name}: {exc}')
            elif self.currentMessage.command == 'commanderror':
                self.onCommandResult(False, self.currentMessage['commandname'], self.currentMessage['errormessage'])
                try:
                    self.commandResult.emit(False, self.currentMessage['commandname'], self.currentMessage['errormessage'])
                except Exception as exc:
                    self._logger.critical(f'Exception while emitting the commandResult signal of device {self.name}: {exc}')
                self._logger.error(f'Error while executing command {self.currentMessage["commandname"]} on device {self.name}: {self.currentMessage["errormessage"]}')
            elif self.currentMessage.command == 'commandfinished':
                self.onCommandResult(False, self.currentMessage['commandname'], self.currentMessage['result'])
                try:
                    self.commandResult.emit(True, self.currentMessage['commandname'], self.currentMessage['result'])
                except Exception as exc:
                    self._logger.critical(f'Exception while emitting the commandResult signal of device {self.name}: {exc}')
                self._logger.debug(f'Command {self.currentMessage["commandname"]} finished successfully on device {self.name}. Result: {self.currentMessage["result"]}')
            elif self.currentMessage.command == 'end':
                self._backend.join()
                self.killTimer(self._timerid)
                try:
                    self.connectionEnded.emit(self.currentMessage['expected'])
                except Exception as exc:
                    self._logger.critical(
                        f'Exception while emitting the connectionEnded signal of device {self.name}: {exc}')
        finally:
            self.currentMessage = None

    @property
    def ready(self) -> bool:
        """Check if all variables have been updated since the start of the device handler"""
        return all([v.timestamp is not None for v in self._variables])

    def __getitem__(self, item: str) -> Any:
        """Get the value of a variable.

        :param item: variable name
        :type item: str
        :return: the value of the variable
        :rtype: any
        :raises DeviceError: if the variable has not been updated yet
        """
        var = [v for v in self._variables if v.name == item][0]
        if var.timestamp is None:
#            self._logger.debug('Available variables: \n'+'\n'.join(sorted([f'    {v.name}' for v in self._variables if v.timestamp is not None])))
#            self._logger.debug('Not available variables: \n'+'\n'.join(sorted([f'    {v.name}' for v in self._variables if v.timestamp is None])))
            raise self.DeviceError(f'Variable {var.name} of device {self.name} has not been updated yet.')
        return [v.value for v in self._variables if v.name == item][0]

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
        self._logger.debug(f'Issuing command: {command} with arguments {args}')
        self._queue_to_backend.put(Message('issuecommand', name=command, args=args))

    def stopbackend(self):
        """Ask the backend process to quit."""
        self._logger.debug(f'Stopping the back-end process')
        self._queue_to_backend.put(Message('end'))

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

    def onCommandResult(self, commandname: str, success: bool, result: str):
        pass

    def toDict(self) -> Dict[str, Any]:
        return {v.name:v.value for v in self._variables}

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 2

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._variables)

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