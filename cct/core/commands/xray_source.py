import traceback

from .command import Command, CommandError, CommandArgumentError, CommandKilledError


class Shutter(Command):
    """Open or close the shutter.

    Invocation: shutter(<state>)

    Arguments:
        <state>: 'close', 'open', True, False or a numeric boolean value

    Remarks: None
    """

    name = 'shutter'

    timeout = 3

    required_devices = ['xray_source']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly one positional argument.'.format(self.name))
        if isinstance(self.args[0], str):
            if self.args[0].upper() in ['OPEN']:
                self.open_needed = True
            elif self.args[0].upper() in ['CLOSE']:
                self.open_needed = False
            else:
                raise CommandArgumentError(self.args[0])
        else:
            self.open_needed = bool(self.args[0])

    def execute(self):
        if self.open_needed:
            self.emit('message', 'Opening shutter.')
        else:
            self.emit('message', 'Closing shutter.')
        self.get_device('xray_source').shutter(self.open_needed)

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'shutter' and newvalue == self.open_needed:
            self.idle_return(newvalue)


class Xrays(Command):
    """Enable or disable X-ray generation

    Invocation: xrays(<state>)

    Arguments:
        <state>: 'on', 'off', True, False or a numeric boolean value

    Remarks: None
    """

    name = 'xrays'

    timeout = 2

    required_devices = ['xray_source']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly one positional argument.'.format(self.name))
        if isinstance(self.args[0], str):
            if self.args[0].upper() in ['ON']:
                self.on_needed = True
            elif self.args[0].upper() in ['OFF']:
                self.on_needed = False
            else:
                raise CommandArgumentError(self.args[0])
        else:
            self.on_needed = bool(self.args[0])

    def execute(self):
        if self.on_needed:
            self.emit('message', 'Turning X-ray generator on.')
        else:
            self.emit('message', 'Turning X-ray generator off.')
        self.get_device('xray_source').set_xrays(self.on_needed)

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'xrays' and newvalue == self.on_needed:
            self.idle_return(newvalue)


class XrayFaultsReset(Command):
    """Reset faults in GeniX

    Invocation: xray_reset_faults()

    Arguments:
        <state>: 'on', 'off', True, False or a numeric boolean value

    Remarks: None
    """

    name = 'xray_reset_faults'

    timeout = 2

    required_devices = ['xray_source']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if self.args:
            raise CommandArgumentError('Command {} does not support positional arguments.'.format(self.name))

    def execute(self):
        self.emit('Trying to reset X-ray generator fault flags.')
        self.get_device('xray_source').reset_faults()

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'faults' and newvalue is False:
            self.idle_return(newvalue)


class XRayPower(Command):
    """Set the power of the X-ray source

    Invocation: xray_power(<state>)

    Arguments:
        <state>: 
            'down', 'off', 0, '0', '0W': turn the power off
            'standby', 'low', 9, '9', '9W': standby (low-power mode)
            'full', 'high', 30, '30', '30W': full-power mode

    Remarks: None
    """

    name = 'xray_power'

    required_devices = ['xray_source']

    pulse_interval = 0.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly one positional argument.'.format(self.name))
        self.args[0] = str(self.args[0])
        if self.args[0].upper() in ['DOWN', 'OFF', '0W', '0']:
            self.command = 'poweroff'
            self.target = 'Power off'
        elif self.args[0].upper() in ['STANDBY', 'LOW', '9W', '9']:
            self.command = 'standby'
            self.target = 'Low power'
        elif self.args[0].upper() in ['FULL', 'HIGH', '30W', '30']:
            self.command = 'full_power'
            self.target = 'Full power'
        else:
            raise CommandArgumentError(self.args[0])

    def validate(self):
        source = self.get_device('xray_source')
        if source.is_busy():
            raise CommandError('Cannot set the X-ray source to {} while busy.'.format(self.target))
        if not source.get_variable('xrays'):
            raise CommandError('Cannot set the X-ray source to {} while X-ray generator is off.'.format(self.target))

    def execute(self):
        self.get_device('xray_source').execute_command(self.command)

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == '_status' and newvalue == self.target:
            self.idle_return(newvalue)

    def on_pulse(self):
        self.emit('pulse', 'Setting X-ray source to {}...'.format(self.target))


class Warmup(Command):
    """Start the warming-up procedure of the X-ray source

    Invocation: xray_warmup()

    Arguments: None

    Remarks: None
    """
    name = 'xray_warmup'

    required_devices = ['xray_source']

    pulse_interval = 0.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if self.args:
            raise CommandArgumentError('Command {} does not support positional arguments.'.format(self.name))

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == '_status' and newvalue == 'Power off':
            self.idle_return(newvalue)

    def validate(self):
        if self.get_device('xray_source').get_variable('_status') != 'Power off':
            raise CommandError('Warm-up can only be started from power off mode')

    def on_pulse(self):
        self.emit('pulse', 'Warming up X-ray source...')

    def execute(self):
        self.get_device('xray_source').execute_command('start_warmup')
        self.emit('message', 'Started warm-up procedure.')

    def kill(self):
        self.get_device('xray_source').execute_command('stop_warmup')
        self.get_device('xray_source').execute_command('poweroff')
        try:
            raise CommandKilledError('Stopped warm-up procedure.')
        except CommandKilledError as cke:
            self.emit('fail', cke, traceback.format_exc())
