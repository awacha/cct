import logging
from typing import List, Optional, Any, Set, Tuple, final

from PyQt5 import QtWidgets, QtGui

from ...core2.devices.device.frontend import DeviceFrontend
from ...core2.instrument.components.motors import Motor
from ...core2.instrument.instrument import Instrument
from ...core2.instrument.components.auth import Privilege

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class WindowRequiresDevices:
    """Convenience mixin class for UI windows


    """
    required_devicenames: Optional[List[str]] = None
    required_devicetypes: Optional[List[str]] = None
    required_motors: Optional[List[str]] = None
    required_privileges: Optional[List[Privilege]] = None
    _idle: bool=True
    instrument: Instrument
    _devices: Set[DeviceFrontend]
    _motors: Set[Motor]
    _required_devices: Set[str]
    _required_motors: Set[str]
    _requirements_satisfied: bool = False

    def __init__(self, **kwargs):
        if self.required_devicenames is None:
            self.required_devicenames = []
        if self.required_devicetypes is None:
            self.required_devicetypes = []
        if self.required_motors is None:
            self.required_motors = []
        self._motors = set()
        self._required_motors = set()
        self._devices = set()
        self._required_devices = set()
        logger.debug('Initializing a device- and motor-requiring window.')
        logger.debug(f'required device names: {self.required_devicenames}')
        logger.debug(f'required device types: {self.required_devicetypes}')
        logger.debug(f'required motors: {self.required_motors}')
        self.instrument = kwargs['instrument']
        self.mainwindow = kwargs['mainwindow']
        devices = {d for d in self.instrument.devicemanager.devices.values()
                   if (d.name in self.required_devicenames)
                   or (d.devicetype in self.required_devicetypes)
                   or ('*' in self.required_devicetypes)
                   or ('*' in self.required_devicenames)}
        motors = {m for m in self.instrument.motors.motors
                  if (m.name in self.required_motors)
                  or ('*' in self.required_motors)}
        for d in devices:
            logger.debug(f'Connecting device {d.name}')
            self._connectDevice(d)
        self.instrument.devicemanager.deviceDisconnected.connect(self.onDeviceDisconnected)
        self.instrument.devicemanager.deviceConnected.connect(self.onDeviceConnected)
        logger.debug('Connecting motors')
        for m in motors:
            assert isinstance(m, Motor)
            self._connectMotor(m)
        logger.debug(f'Connected {len(motors)} motors')
        self.instrument.config.changed.connect(self.onConfigChanged)
        self.instrument.auth.currentUserChanged.connect(self.onUserOrPrivilegesChanged)
        self.instrument.motors.newMotor.connect(self.onNewMotor)
        self.instrument.motors.motorRemoved.connect(self.onMotorRemoved)

    @classmethod
    @final
    def canOpen(cls, instrument: Instrument) -> bool:
        for dt in (cls.required_devicetypes if cls.required_devicetypes is not None else []):
            if dt == '*':
                continue
            if not [d for d in instrument.devicemanager.devices.values() if d.devicetype == dt]:
                logger.debug(f'Cannot instantiate {cls.__name__}: no device of type {dt} available.')
                return False
        for dn in (cls.required_devicenames if cls.required_devicenames is not None else []):
            if dn == '*':
                continue
            if not [d for d in instrument.devicemanager.devices.values() if (d.name == dn)]:
                logger.debug(f'Cannot instantiate {cls.__name__}: no device with name {dn} available.')
                return False
        for mot in (cls.required_motors if cls.required_motors is not None else []):
            if mot == '*':
                continue
            if not [m for m in instrument.motors if (m.name == mot)]:
                logger.debug(f'Cannot instantiate {cls.__name__}: no motors with name {mot} available')
                return False
        for priv in (cls.required_privileges if cls.required_privileges is not None else []):
            if not instrument.auth.hasPrivilege(priv):
                logger.debug(f'Cannot instantiate {cls.__name__}: privilege {priv} is not available')
                return False
        return True

    @final
    def _connectDevice(self, device: DeviceFrontend):
        assert isinstance(device, DeviceFrontend)
        logger.debug(f'connecting device {device.name}')
        device.commandResult.connect(self.onCommandResult)
        device.variableChanged.connect(self.onVariableChanged)
        device.allVariablesReady.connect(self.onAllVariablesReady)
        device.destroyed.connect(self.onDeviceDestroyed)
        self._devices.add(device)
        self._required_devices.add(device.name)

    @final
    def _disconnectDevice(self, device: DeviceFrontend):
        assert isinstance(device, DeviceFrontend)
        try:
            device.commandResult.disconnect(self.onCommandResult)
            device.variableChanged.disconnect(self.onVariableChanged)
            device.allVariablesReady.disconnect(self.onAllVariablesReady)
            device.destroyed.disconnect(self.onDeviceDestroyed)
        except TypeError:
            pass
        try:
            self._devices.remove(device)
        except KeyError:
            pass

    def onDeviceDestroyed(self):
        try:
            self._devices.remove(self.sender())
        except KeyError:
            pass

    @final
    def _connectMotor(self, motor: Motor):
        logger.debug(f'Connecting motor {motor.name}')
        motor.started.connect(self.onMotorStarted)
        motor.stopped.connect(self.onMotorStopped)
        motor.positionChanged.connect(self.onMotorPositionChanged)
        motor.moving.connect(self.onMotorMoving)
        motor.variableChanged.connect(self.onVariableChanged)
        motor.destroyed.connect(self.onMotorDestroyed)
        self._motors.add(motor)
        self._required_motors.add(motor.name)

    def onMotorDestroyed(self):
        try:
            self._motors.remove(self.sender())
        except KeyError:
            pass

    @final
    def _disconnectMotor(self, motor: Motor):
        try:
            motor.started.disconnect(self.onMotorStarted)
            motor.stopped.disconnect(self.onMotorStopped)
            motor.positionChanged.disconnect(self.onMotorPositionChanged)
            motor.moving.disconnect(self.onMotorMoving)
            motor.variableChanged.disconnect(self.onVariableChanged)
            motor.destroyed.disconnect(self.onMotorDestroyed)
        except TypeError:
            pass
        try:
            self._motors.remove(motor)
        except KeyError:
            pass

    @final
    def _checkRequirements(self):
        satisfied = self.canOpen(self.instrument)
        if self._requirements_satisfied != satisfied:
            self._requirements_satisfied = satisfied
            self.onRequirementsSatisfiedChanged(satisfied)

    def onRequirementsSatisfiedChanged(self, satisfied: bool):
        self.setEnabled(satisfied)

    def onCommandResult(self, name: str, success: str, message: str):
        pass

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        pass

    def onDeviceDisconnected(self, devicename: str, expected: bool):
        if devicename in self._required_devices:
            # one of our devices vanished.
            self._checkRequirements()

    @final
    def onDeviceConnected(self, devicename: str):
        device = self.instrument.devicemanager[devicename]
        if (devicename in self._required_devices) or ('*' in self.required_devicenames) \
                or ('*' in self.required_devicetypes) or (device.devicetype in self.required_devicetypes):
            device = self.instrument.devicemanager[devicename]
            self._disconnectDevice(device)
            self._connectDevice(device)
            self._checkRequirements()

    def onAllVariablesReady(self):
        pass

    def onMotorStarted(self, startposition: float):
        pass

    def onMotorStopped(self, success: bool, endposition: float):
        pass

    def onMotorMoving(self, position: float, startposition: float, endposition: float):
        pass

    def onMotorPositionChanged(self, newposition: float):
        pass

    def onConfigChanged(self, path: Tuple[str, ...], newvalue: Any):
        pass

    def onUserOrPrivilegesChanged(self, username: str):
        pass

    @final
    def onNewMotor(self, motorname: str):
        self._checkRequirements()
        if ('*' in self.required_motors) or (motorname in self.required_motors):
            self._connectMotor(self.instrument.motors[motorname])

    def onMotorRemoved(self, motorname: str):
        self._checkRequirements()

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
                    self, 'Confirm close', 'Really close this window? There is a background process working!'):
                closeEvent.accept()
            else:
                closeEvent.ignore()

