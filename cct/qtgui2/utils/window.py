import logging
import traceback
from typing import List, Optional, Any, Tuple, final, Union

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Slot

from ...core2.devices import DeviceFrontend, DeviceType
from ...core2.devices.device.telemetry import TelemetryInformation
from ...core2.instrument.components.auth import Privilege
from ...core2.instrument.components.motors import Motor, MotorRole, MotorDirection
from ...core2.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class WindowRequiresDevices:
    """Convenience mixin class for UI windows

    Some GUI widgets require the availibility of certain devices (e.g. a motor mover window). By specifying this class
    among its parents, the following operations are automated:

    - checking the availability of the required devices on initialization
    - connecting to the most important signals of the devices:
        - variableChanged -> onVariableChanged
        - allVariablesReady -> onAllVariablesReady
        - connectionLost -> onConnectionLost
        - connectionEnded -> onConnectionEnded
        - commandResult -> onCommandResult
        - destroyed -> onDeviceDestroyed
    - disconnecting the signal handlers when the device is disconnected

    In addition to devices, motors can be required in a similar way. Their callback functions are:
        - started -> onMotorStarted: motor started moving
        - stopped -> onMotorStopped: motor stopped moving
        - positionChanged -> onMotorPositionChanged: motor position updated
        - moving -> onMotorMoving: motor position is updated while moving
        - variableChanged -> onVariableChanged: motor variable changed, common callback with device variable changed
        - destroyed -> onMotorDestroyed: motor is destroyed

    Motors and devices can be required using the `required_devicenames` or `required_devicetypes` attributes, set before
    calling __init__. These are lists of strings.

    Even after initialization, the widget keeps a look out on devices/motors: if a required device becomes unavailable,
    either temporarily (unexpected communication error) or terminally (disconnection), the widget becomes disabled.
    Whenever they become available, the widget is reenabled.

    The concept of 'idle' and 'busy' states are also implemented. If the widget is set 'busy' with the `setBusy()`
    method, any attempt to close it will result in a question to the user for confirmation.



    :ivar required_devicenames: list of device names which are required for
    """
    connect_all_devices: bool = False  # regardless of requirements, always connect all available devices
    connect_all_motors: bool = False  # regardless of requirements, always connect all available motors
    required_devicenames: Optional[List[str]] = None  # list of the names of required devices
    required_devicetypes: Optional[
        List[DeviceType]] = None  # list of required device types: at least one device of each type must be present
    required_motors: Optional[
        List[Tuple[MotorRole, MotorDirection]]] = None  # list of required motor roles and directions
    required_privileges: Optional[List[Privilege]] = None  # list of required privileges

    _idle: bool = True  # True if the widget is 'idle'. If False, the user will be asked for confirmation for closing the widget
    instrument: Optional[Instrument] = None  # the `Instrument` instance
    mainwindow: Optional["MainWindow"] = None  # the `MainWindow` instance
    _requirements_satisfied: bool = False  # True if all requirements (devices, motors, privileges) are satisfied
    _sensitive: bool = True  # User-requested enabled/disabled state of the widget. The actual enabled/disabled state is the AND of this and `_requirements_satisfied`

    def __init__(self, **kwargs):
        """Instantiate a device/motor/privilege-aware window

        Keyword arguments:

        :param instrument: the Instrument instance (optional, by default None)
        :type instrument: `Instrument`
        :param mainwindow: the main window instance
        :param mainwindow: the main window instance
        :type mainwindow: `MainWindow`
        """
        try:
            instrument = kwargs.pop('instrument')
        except KeyError:
            instrument = None
        mainwindow = kwargs.pop('mainwindow')
        super().__init__(**kwargs)
        if self.required_devicenames is None:
            self.required_devicenames = []
        if self.required_devicetypes is None:
            self.required_devicetypes = []
        if self.required_motors is None:
            self.required_motors = []
        logger.debug('Initializing a device- and motor-requiring window.')
        logger.debug(f'required device names: {self.required_devicenames}')
        logger.debug(f'required device types: {[dt.name for dt in self.required_devicetypes]}')
        logger.debug(f'required motors: {self.required_motors}')
        if instrument is not None:
            # this check allows off-line usage of the widget, i.e. without a valid 'instrument' instance.
            self.instrument = instrument
            # now try to connect devices and motors
            for dev in self.instrument.devicemanager:
                self._onDeviceAdded(dev.name)
            for mot in self.instrument.motors:
                self._onNewMotor(mot.name)
            # have a look out for added/removed devices and motors
            self.instrument.devicemanager.deviceRemoved.connect(self._onDeviceRemoved)
            self.instrument.devicemanager.deviceAdded.connect(self._onDeviceAdded)
            self.instrument.motors.newMotor.connect(self._onNewMotor)
            self.instrument.motors.motorRemoved.connect(self.onMotorRemoved)

            self.instrument.config.changed.connect(self.onConfigChanged)
            self.instrument.auth.currentUserChanged.connect(self.onUserOrPrivilegesChanged)
        else:
            self.instrument = None
        self.mainwindow = mainwindow

    # ------------ Checking and handling requirements ------------------------------------------------------------------

    @classmethod
    @final
    def checkRequirements(cls) -> bool:
        """Check if the requirements are satisfied for this widget class"""
        logger.debug(f'Rechecking requirements for class {cls.__name__}')
        instrument = Instrument.instance()
        required_devicetypes = [] if cls.required_devicetypes is None else cls.required_devicetypes
        required_devicenames = [] if cls.required_devicenames is None else cls.required_devicenames
        required_motors = [] if cls.required_motors is None else cls.required_motors
        required_privileges = [] if cls.required_privileges is None else cls.required_privileges

        for dt in required_devicetypes:
            if not instrument.devicemanager.devicesOfType(dt, online=True):
                # no on-line devices are found of this type
                logger.debug(f'Cannot instantiate {cls.__name__}: no device of type {dt} available.')
                return False
        for dn in required_devicenames:
            if not [d for d in instrument.devicemanager if (d.devicename == dn) and d.isOnline()]:
                logger.debug(f'Cannot instantiate {cls.__name__}: no device with name {dn} available.')
                return False
        for motrole, motdir in required_motors:
            if not [m for m in instrument.motors if (m.role == motrole) and (m.direction == motdir) and m.isOnline()]:
                logger.debug(
                    f'Cannot instantiate {cls.__name__}: no motors with role {motrole} and direction {motdir} available')
                return False
        for priv in required_privileges:
            if not instrument.auth.hasPrivilege(priv):
                logger.debug(f'Cannot instantiate {cls.__name__}: privilege {priv} is not available')
                return False
        logger.debug(f'Requirements satisfied for class {cls.__name__}')
        return True

    def setSensitive(self, sensitive: Optional[bool] = True):
        """An extended version of QtWidget.setEnabled(): only set the widget enabled (sensitive) if all the requirements
        are satisfied."""
        if (self.instrument is None) and (sensitive is not None):
            return self.setEnabled(sensitive)
        else:
            self._sensitive = sensitive if sensitive is not None else self._sensitive
            return self.setEnabled(self._sensitive and self.checkRequirements())

    def setUnsensitive(self, unsensitive: Optional[bool] = True):
        return self.setSensitive(not unsensitive)

    # ---------- Connecting and disconnecting signal handlers ----------------------------------------------------------

    @final
    def _connectDevice(self, device: DeviceFrontend):
        """Connect the signals of the device to the callback functions"""
        assert isinstance(device, DeviceFrontend)
        logger.debug(f'connecting device {device.name}')
        device.commandResult.connect(self.onCommandResult)
        device.variableChanged.connect(self.onVariableChanged)
        device.allVariablesReady.connect(self.onAllVariablesReady)
        device.connectionLost.connect(self.onConnectionLost)
        device.connectionEnded.connect(self.onConnectionEnded)
        device.telemetry.connect(self.onDeviceTelemetry)

    @final
    def _disconnectDevice(self, device: DeviceFrontend):
        """Disconnect the signals of the device from the callback functions"""
        assert isinstance(device, DeviceFrontend)
        try:
            device.commandResult.disconnect(self.onCommandResult)
            device.variableChanged.disconnect(self.onVariableChanged)
            device.allVariablesReady.disconnect(self.onAllVariablesReady)
            device.connectionLost.disconnect(self.onConnectionLost)
            device.connectionEnded.disconnect(self.onConnectionEnded)
            device.telemetry.disconnect(self.onDeviceTelemetry)
        except (TypeError, RuntimeError):
            pass

    @final
    def connectMotor(self, motor: Union[Motor, str]):
        """Connect the signals of a motor to the callback functions"""
        if isinstance(motor, str):
            motor = self.instrument.motors[motor]
        logger.debug(f'Connecting motor {motor.name} to an instance of class {self.__class__.__name__}')
        motor.started.connect(self.onMotorStarted)
        motor.stopped.connect(self.onMotorStopped)
        motor.positionChanged.connect(self.onMotorPositionChanged)
        motor.moving.connect(self.onMotorMoving)
        motor.variableChanged.connect(self.onVariableChanged)
        motor.cameOnLine.connect(self._onMotorOnLine)
        motor.wentOffLine.connect(self._onMotorOffLine)

    @final
    def disconnectMotor(self, motor: Union[Motor, str]):
        """Disconnect the signals of a motor from the callback functions"""
        if isinstance(motor, str):
            motor = self.instrument.motors[motor]
        try:
            logger.debug(f'Disconnecting motor {motor.name} from an instance of class {self.__class__.__name__}')
            motor.started.disconnect(self.onMotorStarted)
            motor.stopped.disconnect(self.onMotorStopped)
            motor.positionChanged.disconnect(self.onMotorPositionChanged)
            motor.moving.disconnect(self.onMotorMoving)
            motor.variableChanged.disconnect(self.onVariableChanged)
            motor.cameOnLine.disconnect(self._onMotorOnLine)
            motor.wentOffLine.disconnect(self._onMotorOffLine)
        except TypeError:
            pass

    # -------------------------- callback functions from devices and motors -------------------------------------------

    @Slot(object)
    def onDeviceTelemetry(self, telemetry: TelemetryInformation):
        pass

    @Slot()
    def onConnectionLost(self):
        """Called when the connection to a device is lost unexpectedly, but will be reconnected if possible.

        The device should be considered "temporarily out of order".

        The device is `self.sender()`.
        """
        self.setSensitive(None)

    @Slot(bool)
    def onConnectionEnded(self, expected: bool):
        """Called when the connection to a device is closed, without further attempts to reconneect.

        The device should be considered "completely out of order".

        The device is `self.sender()`
        """
        self.setSensitive(None)

    @Slot(bool, str, str)
    def onCommandResult(self, success: bool, name: str, message: str):
        """Called when a command issued to a device is done: either successfully or with an error.

        The device is `self.sender()`
        """
        pass

    @Slot(str, object, object)
    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        """Called when a state variable of a connected device or motor is changed.

        The device or motor is `self.sender()`
        """
        pass

    @final
    @Slot(str, bool)
    def _onDeviceRemoved(self, devicename: str, expected: bool):
        self.setSensitive(None)
        self.onDeviceRemoved(devicename, expected)

    def onDeviceRemoved(self, devicename: str, expected: bool):
        pass

    @final
    @Slot(str)
    def _onDeviceAdded(self, devicename: str):
        device = self.instrument.devicemanager[devicename]
        if (device.devicename in self.required_devicenames) or self.connect_all_devices or (
                device.devicetype in self.required_devicetypes):
            device = self.instrument.devicemanager[devicename]
            self._disconnectDevice(device)
            self._connectDevice(device)
            self.setSensitive(None)
        try:
            self.onDeviceAdded(devicename)
        except Exception as exc:
            logger.critical(f'Exception in callback onDeviceAdded(): {exc}' + traceback.format_exc())

    def onDeviceAdded(self, devicename: str):
        pass

    @final
    @Slot()
    def _onMotorOnLine(self):
        self.setSensitive(None)
        self.onMotorOnLine()

    @final
    @Slot()
    def _onMotorOffLine(self):
        self.setSensitive(None)
        self.onMotorOffLine()

    def onMotorOnLine(self):
        pass

    def onMotorOffLine(self):
        pass

    @Slot()
    def onAllVariablesReady(self):
        self.setSensitive(None)

    @Slot(float)
    def onMotorStarted(self, startposition: float):
        pass

    @Slot(bool, float)
    def onMotorStopped(self, success: bool, endposition: float):
        pass

    @Slot(float, float, float)
    def onMotorMoving(self, position: float, startposition: float, endposition: float):
        pass

    @Slot(float)
    def onMotorPositionChanged(self, newposition: float):
        pass

    @Slot(object, object)
    def onConfigChanged(self, path: Tuple[str, ...], newvalue: Any):
        pass

    @Slot(str)
    def onUserOrPrivilegesChanged(self, username: str):
        pass

    @final
    @Slot(str)
    def _onNewMotor(self, motorname: str):
        logger.debug(f'New motor callback in {self.__class__.__name__}')
        motor = self.instrument.motors[motorname]
        if self.connect_all_motors or ((motor.role, motor.direction) in self.required_motors):
            self.connectMotor(self.instrument.motors[motorname])
        self.setSensitive(None)
        self.onNewMotor(motorname)

    def onNewMotor(self, motorname: str):
        pass

    @Slot(str)
    def onMotorRemoved(self, motorname: str):
        self.setSensitive(None)

    def isIdle(self) -> bool:
        return self._idle

    def setIdle(self):
        self._idle = True

    def setBusy(self):
        self._idle = False

    def closeEvent(self, closeEvent: QtGui.QCloseEvent):
        if self.isIdle():
            closeEvent.accept()
        else:
            if QtWidgets.QMessageBox.question(
                    self.window(), 'Confirm close', 'Really close this window? There is a background process working!'):
                closeEvent.accept()
            else:
                closeEvent.ignore()
