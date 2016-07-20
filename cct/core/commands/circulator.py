import logging
import time
import traceback

from .command import Command, CommandArgumentError, CommandError

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

    required_devices = ['temperature']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) > 1:
            raise CommandArgumentError(
                'Number of arguments to command {} must be 0 or 1, got {:d}'.format(
                    self.name, len(self.args)))
        if self.args:
            if isinstance(self.args[0], str):
                if self.args[0].upper() in ['START', 'ON']:
                    self.requested_state = True
                elif self.args[0].upper() in ['STOP', 'OFF']:
                    self.requested_state = False
                else:
                    raise CommandArgumentError('Invalid argument for command {}: {}'.format(self.name, self.args[0]))
            else:
                try:
                    self.requested_state = bool(self.args[0])
                except Exception as exc:
                    raise CommandArgumentError(
                        'Invalid argument type for command {}: {}'.format(self.name, type(self.args[0])))
        else:
            self.requested_state = None

    def execute(self):
        if self.requested_state is None:
            var = self.interpreter.instrument.get_device('temperature').get_variable('_state')
            if var == 'running':
                self.idle_return(True)
            elif var == 'stopped':
                self.idle_return(False)
            else:
                raise CommandError('Unexpected state: {}'.format(var))
            return
        if self.requested_state:
            self.emit('message', 'Starting thermocontrolling circulator.')
            self.interpreter.instrument.get_device('temperature').execute_command('start')
        else:
            self.emit('message', 'Stopping thermocontrolling circulator.')
            self.interpreter.instrument.get_device('temperature').execute_command('stop')

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == '_status' and newvalue == 'start' and self.requested_state:
            self.cleanup(True)
        elif variablename == '_status' and newvalue == 'stop' and not self.requested_state:
            self.cleanup(False)
        else:
            pass
        return False


class Temperature(Command):
    """Get the temperature (in °C units)

    Invocation: temperature()

    Arguments:
        None

    Remarks: None
    """

    name = 'temperature'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if self.args:
            raise CommandArgumentError('Command {} does not support positional arguments.'.format(self.name))

    def execute(self):
        self.idle_return(self.interpreter.instrument.get_device('temperature').get_variable('temperature'))


class SetTemperature(Command):
    """Set the target temperature (in °C units)

    Invocation: settemp(<setpoint>)

    Arguments:
        <setpoint>: the requested target temperature.

    Remarks: None
    """

    name = 'settemp'

    timeout = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} needs exactly one positional argument.'.format(self.name))
        self.target_temperature = float(self.args[0])

    def validate(self):
        if (self.target_temperature > self.interpreter.instrument.get_device('temperature').get_variable('highlimit') or
                    self.target_temperature < self.interpreter.instrument.get_device('temperature').get_variable(
                    'lowlimit')):
            raise CommandArgumentError('Desired temperature is outside the allowed range.')
        return True

    def execute(self):
        self.interpreter.instrument.get_device('temperature').set_variable('setpoint', self.target_temperature)

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'setpoint':
            if abs(newvalue - self.target_temperature) > 0.01:
                try:
                    raise CommandError(
                        'Could not set target temperature. Desired: {:f}. Got: {:f}'.format(
                            self.target_temperature, newvalue))
                except CommandError as ce:
                    self.emit('fail', ce, traceback.format_exc())
            else:
                self.cleanup(newvalue)


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

    pulse = 1

    required_devices = ['temperature']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 2:
            raise CommandArgumentError('Command {} needs exactly two positional arguments.'.format(self.name))
        try:
            self.tolerance = float(self.args[0])
            self.delay = float(self.args[0])
        except ValueError:
            raise CommandArgumentError('Invalid argument to command {}'.format(self.name))
        self.in_tolerance_interval = 0
        self.temperature = None

    def execute(self):
        self.temperature = self.interpreter.instrument.get_device('temperature').get_variable('temperature')

    def on_pulse(self):
        if self.in_tolerance_interval == 0:
            self.emit('pulse', 'Waiting for temperature stability: {:.2f} °C'.format(self.temperature))
        else:
            spent_time = (time.monotonic() - self.in_tolerance_interval)
            remainingtime = (self.delay - spent_time)
            fraction = spent_time / self.delay
            if fraction < 1:
                self.emit('progress',
                          'Temperature stability reached ({:.2f} °C), waiting for {:.0f} seconds'.format(
                              self.temperature, remainingtime), fraction)
            else:
                self.cleanup(self.temperature)
        return True

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'temperature':
            if abs(newvalue - device.get_variable('setpoint')) > self.tolerance:
                self.in_tolerance_interval = 0
            elif self.in_tolerance_interval == 0:
                self.in_tolerance_interval = time.monotonic()
        return False
