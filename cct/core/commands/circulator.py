import logging
import time

from gi.repository import GLib

from .command import Command
from .script import Script

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class StartStop(Command):
    """Start or stop the circulator

    Invocation: circulator(<state>)

    Arguments:
        <state>: 'start', 'on', True, 1 or 'stop', 'off', False, 0
    """
    name = 'circulator'
    timeout = 5

    def execute(self, interpreter, arglist, instrument, namespace):
        if isinstance(arglist[0], str):
            if arglist[0].upper() in ['START', 'ON']:
                requestedstate = True
            elif arglist[0].upper() in ['STOP', 'OFF']:
                requestedstate = False
            else:
                raise NotImplementedError(arglist[0])
        elif isinstance(arglist[0], bool):
            requestedstate = arglist[0]
        elif isinstance(arglist[0], float) or isinstance(arglist[0], int):
            requestedstate = bool(arglist[0])
        else:
            raise NotImplementedError(arglist[0])
        self._require_device(instrument, 'haakephoenix')
        self._install_timeout_handler(5)
        self._check_for_variable = '_status'
        if requestedstate:
            self._check_for_value = 'running'
            self.emit('message', 'Starting thermocontrolling circulator.')
            instrument.devices['haakephoenix'].execute_command('start')
        else:
            self._check_for_value = 'stopped'
            self.emit('message', 'Stopping thermocontrolling circulator.')
            instrument.devices['haakephoenix'].execute_command('stop')


class Temperature(Script):
    """Get the temperature (in °C units)

    Invocation: temperature()

    Arguments:
        None

    Remarks: None
    """

    name = 'temperature'

    script = "getvar('haakephoenix','temperature_internal')"


class SetTemperature(Script):
    """Set the target temperature (in °C units)

    Invocation: settemp(<setpoint>)

    Arguments:
        <setpoint>: the requested target temperature.

    Remarks: None
    """

    name = 'settemp'

    script = "setvar('haakephoenix','setpoint', _scriptargs[0])"


class WaitTemperature(Command):
    """Wait until the temperature stabilizes

    Invocation: wait_temp(<tolerance>, <delay>)

    Arguments:
        <tolerance>: the radius in which the temperature must reside
        <delay>: the time interval

    Remarks:
        In the first phase, the command waits until the temperature read from
        the controller approaches the set-point by <tolerance>. If this
        happens, it will wait <delay> seconds, and constantly check if the
        temperature is still in the tolerance interval. If it gets out of it,
        the first phase is repeated. If, at the end of the delay,
        the temperature is still inside the interval, the command finishes.
    """
    name = "wait_temp"

    def execute(self, interpreter, arglist, instrument, namespace):
        self.tolerance = float(arglist[0])
        self.delay = float(arglist[1])
        self._require_device(instrument, 'haakephoenix')
        self._in_tolerance_interval = None
        self._pulser = GLib.timeout_add(1000, self.pulser)
        self._instrument = instrument

    def pulser(self):
        if self._in_tolerance_interval is None:
            self.emit('pulse', 'Waiting for temperature stability: {:.2f} °C'.format(
                self._instrument.devices['haakephoenix'].get_variable('temperature')))
        else:
            remainingtime = (self.delay - (time.monotonic() - self._in_tolerance_interval))
            fraction = (time.monotonic() - self._in_tolerance_interval) / self.delay
            self.emit('progress',
                      'Temperature stability reached ({:.2f} °C), waiting for {:.0f} seconds'.format(
                          self._instrument.devices['haakephoenix'].get_variable('temperature'),
                          remainingtime),
                      fraction)
        self.on_variable_change(self._instrument.devices['haakephoenix'], 'temperature',
                                self._instrument.devices['haakephoenix'].get_variable('temperature'))
        return True

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'temperature':
            if abs(newvalue - device.get_variable('setpoint')) > self.tolerance:
                self._in_tolerance_interval = None
            elif self._in_tolerance_interval is None:
                self._in_tolerance_interval = time.monotonic()
            elif (time.monotonic() - self._in_tolerance_interval) > self.delay:
                self._uninstall_pulse_handler()
                self._unrequire_device(device.name)
                GLib.source_remove(self._pulser)
                self.emit('return', newvalue)
        return False

    def kill(self):
        self._uninstall_pulse_handler()
        self._unrequire_device()
        GLib.source_remove(self._pulser)
        self.emit('return', None)
        return False
