import logging
from typing import List, Optional, Any, Set, Tuple

from ...core2.devices.device.frontend import DeviceFrontend
from ...core2.instrument.components.motors import Motor
from ...core2.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class WindowRequiresDevices:
    required_devicenames: Optional[List[str]] = None
    required_devicetypes: Optional[List[str]] = None
    required_motors: Optional[List[str]] = None

    instrument: Instrument
    _required_devices: Set[str]
    _requirements_satisfied: bool = False

    def __init__(self, **kwargs):
        logger.debug('Initializing a device- and motor-requiring window.')
        logger.debug(f'required device names: {self.required_devicenames}')
        logger.debug(f'required device types: {self.required_devicetypes}')
        logger.debug(f'required motors: {self.required_motors}')
        instrument = kwargs['instrument']
        assert isinstance(instrument, Instrument)
        self.instrument = instrument
        devices = {d for d in instrument.devicemanager.devices.values()
                   if (d.name in (self.required_devicenames if self.required_devicenames is not None else []))
                   or (d.devicetype in (self.required_devicetypes if self.required_devicetypes is not None else []))}
        motors = {m for m in instrument.motors.motors if m.name in self.required_motors} if self.required_motors else set()
        self._required_devices = set()
        for d in devices:
            logger.debug(f'Connecting device {d.name}')
            self._connectDevice(d)
        if devices:
            instrument.devicemanager.deviceDisconnected.connect(self.onDeviceDisconnected)
            instrument.devicemanager.deviceConnected.connect(self.onDeviceConnected)
        logger.debug('Connecting motors')
        for m in motors:
            assert isinstance(m, Motor)
            logger.debug(f'Connecting motor {m.name}')
            m.started.connect(self.onMotorStarted)
            m.stopped.connect(self.onMotorStopped)
            m.positionChanged.connect(self.onMotorPositionChanged)
            m.moving.connect(self.onMotorMoving)
            m.variableChanged.connect(self.onVariableChanged)
        logger.debug(f'Connected {len(motors)} motors')
        self.instrument.config.changed.connect(self.onConfigChanged)

    @classmethod
    def canOpen(cls, instrument: Instrument) -> bool:
        for dt in (cls.required_devicetypes if cls.required_devicetypes is not None else []):
            if not [d for d in instrument.devicemanager.devices.values() if d.devicetype == dt]:
                logger.debug(f'Cannot instantiate {cls.__name__}: no device of type {dt} available.')
                return False
        for dn in (cls.required_devicenames if cls.required_devicenames is not None else []):
            if not [d for d in instrument.devicemanager.devices.values() if d.name == dn]:
                logger.debug(f'Cannot instantiate {cls.__name__}: no device with name {dn} available.')
                return False
        for mot in (cls.required_motors if cls.required_motors is not None else []):
            if not [m for m in instrument.motors if m.name == mot]:
                logger.debug(f'Cannot instantiate {cls.__name__}: no motors with name {mot} available')
                return False
        return True

    def _connectDevice(self, device: DeviceFrontend):
        assert isinstance(device, DeviceFrontend)
        device.commandResult.connect(self.onCommandResult)
        device.variableChanged.connect(self.onVariableChanged)
        device.allVariablesReady.connect(self.onAllVariablesReady)
        self._required_devices.add(device.name)

    def _disconnectDevice(self, device: DeviceFrontend):
        assert isinstance(device, DeviceFrontend)
        device.commandResult.disconnect(self.onCommandResult)
        device.variableChanged.disconnect(self.onVariableChanged)
        device.allVariablesReady.disconnect(self.onAllVariablesReady)

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

    def onDeviceConnected(self, devicename: str):
        if devicename in self._required_devices:
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
