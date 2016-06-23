from .command import Command
from .script import Script


class Vacuum(Script):
    """Get the vacuum pressure (in mbars)

    Invocation: vacuum()

    Arguments:
        None

    Remarks: None
    """

    name = 'vacuum'

    script = "getvar('tpg201','pressure')"


class WaitVacuum(Command):
    """Wait until the vacuum pressure becomes lower than a given limit

    Invocation: wait_vacuum(<pressure_limit>)

    Arguments:
        <pressure_limit>: the upper limit of the allowed pressure (exclusive)

    Remarks: None
    """

    name = 'wait_vacuum'

    def execute(self, interpreter, arglist, instrument, namespace):
        self._limit = float(arglist[0])
        assert (self._limit > 0)
        self._device_connections = [instrument.devices['tpg201'].connect('variable-change', self.on_variable_change),
                                    instrument.devices['tpg201'].connect('error', self.on_error)]
        self._device = instrument.devices['tpg201']
        self._install_pulse_handler(self._pulsemessage, 1)
        self.emit('message', 'Starting wait for vacuum')

    def _pulsemessage(self):
        return 'Waiting for vacuum to get below {:.3f} mbar. Currently: {:.3f} mbar'.format(
            self._limit, self._device.get_variable('pressure'))

    def on_error(self, device, propname, exc, tb):
        self.emit('fail', exc, tb)

    def _cleanup(self):
        try:
            for dc in self._device_connections:
                self._device.disconnect(dc)
            del self._device_connections
            del self._device
        except AttributeError:
            pass
        self._uninstall_pulse_handler()

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'pressure' and newvalue < self._limit:
            self._cleanup()
            self.emit('return', newvalue)

    def kill(self):
        self._cleanup()
        self.emit('return', None)
