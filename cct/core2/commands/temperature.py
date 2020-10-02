import logging
import time
from typing import Any, Optional

from PyQt5 import QtCore

from .command import Command, InstantCommand
from .commandargument import StringChoicesArgument, FloatArgument
from ..devices.thermostat.haakephoenix.frontend import HaakePhoenix

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ThermostatCommand(Command):
    def thermostat(self) -> HaakePhoenix:
        try:
            return self.instrument.devicemanager.temperature()
        except (KeyError, IndexError):
            raise self.CommandException('Thermostat not found')

    def connectThermostat(self):
        self.thermostat().startStop.connect(self.onThermostatStartStop)
        self.thermostat().temperatureChanged.connect(self.onThermostatTemperatureChanged)
        self.thermostat().commandResult.connect(self.onThermostatCommandResult)
        self.thermostat().variableChanged.connect(self.onThermostatVariableChanged)

    def onThermostatStartStop(self, running: bool):
        pass

    def onThermostatTemperatureChanged(self, temperature: float):
        pass

    def onThermostatCommandResult(self, success: bool, commandname: str, message: str):
        pass

    def onThermostatVariableChanged(self, name: str, newvalue: Any, previousvalue: Any):
        pass

    def disconnectThermostat(self):
        self.thermostat().startStop.disconnect(self.onThermostatStartStop)
        self.thermostat().temperatureChanged.disconnect(self.onThermostatTemperatureChanged)
        self.thermostat().commandResult.disconnect(self.onThermostatCommandResult)
        self.thermostat().variableChanged.disconnect(self.onThermostatVariableChanged)


class StartStop(ThermostatCommand):
    name = 'circulator'
    description = 'Start or stop the circulator'
    arguments = [StringChoicesArgument('state', 'Start or stop', ['start', 'stop'])]
    requestedstate: bool
    sentcommand: str

    def initialize(self, state: str):
        self.connectThermostat()
        try:
            if state.lower() == 'start':
                if self.thermostat().isRunning():
                    self.message.emit('Thermostat already running')
                    self.disconnectThermostat()
                    self.finish(True)
                else:
                    self.sentcommand = 'start'
                    self.message.emit('Starting thermostat circulator')
                    self.progress.emit('Starting thermostat circulator', 0, 0)
                    self.requestedstate = True
                    self.thermostat().startCirculator()
            elif state.lower() == 'stop':
                if not self.thermostat().isRunning():
                    self.message.emit('Thermostat already stopped')
                    self.disconnectThermostat()
                    self.finish(False)
                else:
                    self.sentcommand = 'stop'
                    self.message.emit('Stopping thermostat circulator')
                    self.progress.emit('Stopping thermostat circulator', 0, 0)
                    self.requestedstate = False
                    self.thermostat().stopCirculator()
            else:
                raise self.CommandException(f'Invalid argument for state: "{state}"')
        except:
            self.disconnectThermostat()
            raise

    def onThermostatStartStop(self, running: bool):
        if self.requestedstate and running:
            self.message.emit('Thermostat started.')
            self.disconnectThermostat()
            self.finish(True)
        elif (not self.requestedstate) and (not running):
            self.message.emit('Thermostat stopped.')
            self.disconnectThermostat()
            self.finish(False)
        else:
            self.disconnectThermostat()
            self.fail('Cannot start/stop thermostat.')

    def onThermostatCommandResult(self, success: bool, commandname: str, message: str):
        if commandname != self.sentcommand:
            logger.warning(f'Reply from an unexpected command {commandname} instead from {self.sentcommand}.')
        elif not success:
            self.disconnectThermostat()
            self.fail('Cannot start/stop thermostat.')
        else:
            pass  # wait for the change in the status.


class Temperature(InstantCommand):
    name = 'temperature'
    description = 'Get the temperature in °C units'
    arguments = []

    def run(self) -> float:
        temp = self.instrument.devicemanager.temperature().temperature()
        self.message.emit(f'Temperature is {temp:.2f}°C')
        return temp


class SetTemperature(ThermostatCommand):
    name = 'settemp'
    arguments = [FloatArgument('setpoint', 'The requested target temperature')]
    description = 'Set the target temperature (in °C units)'
    desiredsetpoint: float

    def initialize(self, setpoint: float):
        self.connectThermostat()
        self.desiredsetpoint = setpoint
        try:
            if abs(self.thermostat().setpoint() - setpoint) < 0.01:
                self.message.emit(f'Setpoint already set to {self.thermostat().setpoint():.2f}°C.')
                self.finish(setpoint)
            else:
                self.thermostat().setSetpoint(setpoint)
                self.progress.emit(f'Setting thermostat setpoint to {setpoint:.2f}°C')
        except:
            self.disconnectThermostat()
            raise

    def onThermostatVariableChanged(self, name: str, newvalue: Any, previousvalue: Any):
        if (name == 'setpoint') and (abs(newvalue - self.desiredsetpoint) < 0.01):
            self.finish(newvalue)
        else:
            pass

    def onThermostatCommandResult(self, success: bool, commandname: str, message: str):
        if commandname != 'setpoint':
            logger.warning(f'Reply from an unexpected command {commandname} instead from {self.sentcommand}.')
        elif not success:
            self.disconnectThermostat()
            self.fail('Cannot set setpoint on the thermostat.')
        else:
            pass  # wait until we get the new setpoint value


class WaitTemperature(ThermostatCommand):
    name = 'wait_temp'
    arguments = [FloatArgument('tolerance', 'the radius in which the temperature must reside'),
                 FloatArgument('delay', 'the time interval')]
    description = 'Wait until the temperature stabilizes'
    tolerance: float
    delay: float
    setpoint: float
    intervalreachedat: Optional[float]

    def initialize(self, tolerance: float, delay: float):
        self.tolerance = tolerance
        self.delay = delay
        self.setpoint = self.thermostat().setpoint()
        self.intervalreachedat = None

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        if self.intervalreachedat is None:
            return
        remainingtime = self.delay - (time.monotonic() - self.intervalreachedat)
        if remainingtime <= 0:
            self.finish(True)
        else:
            self.progress.emit(f'Ensuring temperature stability. Remaining time: {remainingtime:.2f} seconds',
                               int(1000*(remainingtime/self.delay)), 1000)

    def onThermostatVariableChanged(self, name: str, newvalue: Any, previousvalue: Any):
        if name == 'setpoint':
            self.setpoint = newvalue
            self.intervalreachedat = None
            self.message.emit('Setpoint changed in the thermostat, starting over...')
            self.progress.emit('Waiting for temperature to reach the interval around the setpoint...', 0, 0)
        elif name == 'temperature':
            if (self.intervalreachedat is None) and (abs(self.setpoint - newvalue) <= self.tolerance):
                self.intervalreachedat = time.monotonic()
                self.message.emit('Interval around the setpoint reached.')
                self.progress.emit(f'Ensuring temperature stability. Remaining time: {self.delay:.2f} seconds', 0, 1000)
            elif (self.intervalreachedat is not None) and (abs(self.setpoint - newvalue) > self.tolerance):
                self.intervalreachedat = None
                self.message.emit('Temperature is out of bounds, starting over.')
                self.progress.emit('Waiting for temperature to reach the interval around the setpoint...', 0, 0)
            else:
                pass

