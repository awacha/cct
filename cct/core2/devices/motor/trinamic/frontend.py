import logging
from typing import Tuple, Any

from .backend import TMCM351Backend, TMCM6110Backend, TrinamicMotorControllerBackend
from .conversion import UnitConverter
from ..generic.frontend import MotorController


class TrinamicMotor(MotorController):
    _converters: Tuple[UnitConverter, ...]
    backendclass: TrinamicMotorControllerBackend
    loglevel = logging.INFO
    vendor = 'Trinamic Ltd.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._converters = tuple(
            [
                UnitConverter(
                    self.backendclass.topRMScurrent,
                    self.backendclass.full_step_size,
                    self.backendclass.clock_frequency
                ) for i in range(self.backendclass.Naxes)])

    def setPulseDivisor(self, motor: int, value: int):
        if value < 0 or value > 13:
            raise ValueError(f'Invalid value for pulse divisor: {value}')
        self.issueCommand('set_pulse_divisor', motor, value)

    def setRampDivisor(self, motor: int, value: int):
        if value < 0 or value > 13:
            raise ValueError(f'Invalid value for ramp divisor: {value}')
        self.issueCommand('set_ramp_divisor', motor, value)

    def setMicroStepResolution(self, motor: int, value: int):
        if value < 0 or value > 8:
            raise ValueError(f'Invalid value for microstep resolution: {value}')
        self.issueCommand('set_microstep_resolution', motor, value)

    def setMaxCurrent(self, motor: int, value: float):
        if value < 0 or value > 255:
            raise ValueError(f'Invalid value for current: {value}')
        self.issueCommand('set_max_current', motor, value)

    def setStandbyCurrent(self, motor: int, value: float):
        if value < 0 or value > 255:
            raise ValueError(f'Invalid value for current: {value}')
        self.issueCommand('set_standby_current', motor, value)

    def setRightSwitchEnable(self, motor: int, state: bool):
        self.issueCommand('set_right_switch_disabled', motor, not state)

    def setLeftSwitchEnable(self, motor: int, state: bool):
        self.issueCommand('set_left_switch_disabled', motor, not state)

    def setFreewheelingDelay(self, motor: int, delay: float):
        if delay < 0 or delay > 65.535:
            raise ValueError(f'Invalid value for current: {delay}')
        self.issueCommand('set_freewheeling_delay', motor, int(delay * 1000))

    def setMaxSpeed(self, motor: int, value: float):
        if value < 0 or value > 2047:
            raise ValueError(f'Invalid value for speed: {value}')
        self.issueCommand('set_max_speed', motor, value)

    def setMaxAcceleration(self, motor: int, value: float):
        if value < 0 or value > 2047:
            raise ValueError(f'Invalid value for acceleration: {value}')
        self.issueCommand('set_max_acceleration', motor, value)

    def speedRange(self, motor: int) -> Tuple[float, float, float]:
        return 0, self._converters[motor].maximumSpeed(), self._converters[motor].speedStep()

    def accelerationRange(self, motor: int) -> Tuple[float, float, float]:
        return 0, self._converters[motor].maximumAcceleration(), self._converters[motor].accelerationStep()

    def currentRange(self, motor: int) -> Tuple[float, float, float]:
        return 0, self._converters[motor].maximumCurrent(), self._converters[motor].currentStep()

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        if '$' in variablename:
            basename, motor = variablename.split('$', 1)
            motor = int(motor)
            if basename == 'pulsedivisor':
                self._converters[motor].pulsedivisor = newvalue
            elif basename == 'rampdivisor':
                self._converters[motor].rampdivisor = newvalue
            elif basename == 'microstepresolution':
                self._converters[motor].microstepresolution = newvalue
            else:
                pass
        return super().onVariableChanged(variablename, newvalue, previousvalue)

    def unitConverter(self, index: int) -> UnitConverter:
        return self._converters[index]


class TMCM351(TrinamicMotor):
    backendclass = TMCM351Backend
    devicename = 'TMCM351'


class TMCM6110(TrinamicMotor):
    backendclass = TMCM6110Backend
    devicename = 'TMCM6110'
