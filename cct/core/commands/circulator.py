from .command import Command
from .script import Script


class StartStop(Command):
    """Start or stop the circulator

    Invocation: circulator(<state>)

    Arguments:
        <state>: 'start', 'on', True, 1 or 'stop', 'off', False, 0
    """
    name = 'circulator'
    timeout=5
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
