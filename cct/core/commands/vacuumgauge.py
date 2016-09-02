from .command import Command, CommandArgumentError


class Vacuum(Command):
    """Get the vacuum pressure (in mbars)

    Invocation: vacuum()

    Arguments:
        None

    Remarks: None
    """

    name = 'vacuum'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if self.args:
            raise CommandArgumentError('Command {} does not support positional arguments.'.format(self.name))

    def execute(self):
        self.idle_return(self.get_device('vacuum').get_variable('pressure'))


class WaitVacuum(Command):
    """Wait until the vacuum pressure becomes lower than a given limit

    Invocation: wait_vacuum(<pressure_limit>)

    Arguments:
        <pressure_limit>: the upper limit of the allowed pressure (exclusive)

    Remarks: None
    """

    name = 'wait_vacuum'

    pulse_interval = 0.5

    required_devices = ['vacuum']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly one positional argument.'.format(self.name))
        self.threshold = float(self.args[0])
        if self.threshold <= 0:
            raise CommandArgumentError('Pressure threshold must be positive.')

    def execute(self):
        self.emit('message', 'Starting wait for vacuum')

    def on_pulse(self):
        self.emit('pulse', 'Waiting for vacuum to get below {:.3f} mbar. Currently: {:.3f} mbar'.format(
            self.threshold, self.get_device('vacuum').get_variable('pressure')))
        return True

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'pressure' and newvalue < self.threshold:
            self.idle_return(newvalue)
