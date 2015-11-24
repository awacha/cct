import logging

from gi.repository import Gtk, GLib

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from ..core.toolframe import ToolFrame
from ...core.services.accounting import PrivilegeLevel

class ShutterBeamstop(ToolFrame):
    def _init_gui(self, *args):
        try:
            self._connections = {
                self._instrument.devices['genix']: [
                    self._instrument.devices['genix'].connect('variable-change', self.on_genix_variable_change),
                ],
                self._instrument.motors['BeamStop_Y']: [
                    self._instrument.motors['BeamStop_Y'].connect('position-change', self.on_motor_position_change),
                ],
                self._instrument.motors['BeamStop_X']: [
                    self._instrument.motors['BeamStop_X'].connect('position-change', self.on_motor_position_change),
                ],
            }
            # self.on_motor_position_change(None, None)
            # self.on_genix_variable_change(self._instrument.devices['genix'], 'shutter',
            #                              self._instrument.devices['genix'].get_variable('shutter'))
        except KeyError:
            self._widget.set_sensitive(False)
        self._privlevelconnection = self._instrument.accounting.connect('privlevel-changed', self.on_privlevel_changed)
        self.on_privlevel_changed(self._instrument.accounting, self._instrument.accounting.get_privilegelevel())

    def on_privlevel_changed(self, accounting, newprivlevel):
        if not accounting.has_privilege(PrivilegeLevel.BEAMSTOP):
            self._builder.get_object('beamstop_in_button').set_sensitive(False)
            self._builder.get_object('beamstop_out_button').set_sensitive(False)
        else:
            self.on_motor_position_change(None, None)

    def on_unmap(self, widget):
        try:
            for dev in list(self._connections):
                for c in self._connections[dev]:
                    dev.disconnect(c)
                del self._connections[dev]
            self._connections = {}
        except AttributeError:
            pass
        try:
            self._instrument.accounting.disconnect(self._privlevelconnection)
            del self._privlevelconnection
        except AttributeError:
            pass

    def on_genix_variable_change(self, genix, varname, value):
        if varname == 'shutter':
            self._builder.get_object('shutter_switch').set_state(value)

    def on_motor_position_change(self, motor, pos):
        try:
            x = self._instrument.motors['BeamStop_X'].where()
            y = self._instrument.motors['BeamStop_Y'].where()
        except KeyError:
            GLib.timeout_add(3000, lambda: self.on_motor_position_change(motor, pos))
            return False

        if ((abs(x - self._instrument.config['beamstop']['in'][0]) < 0.001)
            and (abs(y - self._instrument.config['beamstop']['in'][1]) < 0.001)):
            self._builder.get_object('beamstopstate_image').set_from_icon_name('beamstop-in', Gtk.IconSize.BUTTON)
            self._builder.get_object('beamstop_in_button').set_sensitive(False)
            self._builder.get_object('beamstop_out_button').set_sensitive(True)
        elif ((abs(x - self._instrument.config['beamstop']['out'][0]) < 0.001)
              and (abs(y - self._instrument.config['beamstop']['out'][1]) < 0.001)):
            self._builder.get_object('beamstopstate_image').set_from_icon_name('beamstop-out', Gtk.IconSize.BUTTON)
            self._builder.get_object('beamstop_in_button').set_sensitive(True)
            self._builder.get_object('beamstop_out_button').set_sensitive(False)
        else:
            self._builder.get_object('beamstopstate_image').set_from_icon_name('beamstop-inconsistent',
                                                                               Gtk.IconSize.BUTTON)
            self._builder.get_object('beamstop_in_button').set_sensitive(True)
            self._builder.get_object('beamstop_out_button').set_sensitive(True)
        return False

    def on_shutter_switch_set_state(self, switch, value):
        self._instrument.devices['genix'].shutter(value)
        return True

    def on_beamstop_in(self, button):
        self._instrument.interpreter.execute_command('beamstop("in")')

    def on_beamstop_out(self, button):
        self._instrument.interpreter.execute_command('beamstop("out")')
