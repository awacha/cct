from gi.repository import GLib
from .command import Command
from ..devices.device import DeviceError
import traceback


class GetVariable(Command):
    name = 'getvar'

    timeout = 60

    def execute(self, instrument, arglist, namespace):
        devicename = arglist[0]
        variablename = arglist[1]

        self._connection = instrument.devices[
            devicename].connect('variable-change', self.on_variable_change, variablename)
        self._timeout = GLib.timeout_add(
            self.timeout * 1000, lambda dev=instrument.devices[devicename]: self.on_timeout(dev))
        instrument.devices[devicename].refresh_variable(variablename)

    def on_variable_change(self, device, variable, newvalue, expectedvariable):
        if variable == expectedvariable:
            try:
                device.disconnect(self._connection)
                del self._connection
            except AttributeError:
                pass
            try:
                GLib.source_remove(self._timeout)
                del self._timeout
            except AttributeError:
                pass
            self.emit('return', newvalue)
        return False

    def on_timeout(self, device):
        try:
            device.disconnect(self._conn)
            del self._conn
        except AttributeError:
            pass
        try:
            # this way we can generate a traceback. Ugly, I know.
            raise DeviceError('Shutter timeout')
        except DeviceError as exc:
            self.emit('fail', exc, traceback.format_exc())
        self.emit('return', None)
        return False
