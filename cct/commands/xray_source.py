'''
Created on Oct 15, 2015

@author: labuser
'''
import traceback
from gi.repository import GLib
from ..devices.device import DeviceError
from .command import Command


class Shutter(Command):
    """Open or close the shutter.

    Invocation: shutter(<state>)

    Arguments:
        <state>: 'close', 'open', True, False or a numeric boolean value

    Remarks:
        None
    """

    name = 'shutter'

    timeout = 2

    def execute(self, instrument, arglist, namespace):
        if arglist[0] == 'close':
            requested_state = False
        elif arglist[0] == 'open':
            requested_state = True
        elif isinstance(arglist, int) or isinstance(arglist, bool) or isinstance(arglist, float):
            requested_state = bool(arglist)
        self._conn = [instrument.xray_source.connect(
            'variable-change', self.on_shutter, requested_state),
            instrument.xray_source.connect('error', self.on_error)]
        self._timeout = GLib.timeout_add(
            self.timeout * 1000, lambda xrs=instrument.xray_source: self.on_timeout(xrs))
        instrument.xray_source.shutter(requested_state)

    def on_error(self, xray_source, propertyname, exception):
        self.emit('fail', exception, propertyname)

    def on_shutter(self, xray_source, variable, value, requested_state):
        if variable == 'shutter':
            if value == requested_state:
                try:
                    for c in self._conn:
                        xray_source.disconnect(c)
                    del self._conn
                except AttributeError:
                    pass
                try:
                    GLib.source_remove(self._timeout)
                    del self._timeout
                except AttributeError:
                    pass
                self.emit('return', value)
            return False
        else:
            return False

    def on_timeout(self, xray_source):
        try:
            xray_source.disconnect(self._conn)
            del self._conn
        except AttributeError:
            pass
        try:
            # this way we can generate a traceback. Ugly, I know.
            raise DeviceError('Shutter timeout')
        except DeviceError as exc:
            self.emit('fail', exc, traceback.format_exc())
        self.emit('return', xray_source.get_variable('shutter'))
        return False


class SetPower(Command):
    """Command to set the power of the X-ray source"""

    name = 'xray_power'

    def execute(self, instrument, arglist, namespace):
        xray_source = instrument.xray_source

        if arglist[0] in ['down', 'off', 0, '0', '0W']:
            pass
        elif arglist[0] in ['standby', 'low', 9, '9', '9W']:
            pass
        elif arglist[0] in ['full', 'high', 30, '30', '30W']:
            pass
