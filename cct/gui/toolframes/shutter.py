import logging
from typing import Optional

from gi.repository import Gtk, GLib

from ..core.dialogs import error_message
from ..core.toolframe import ToolFrame
from ...core.commands.motor import Beamstop
from ...core.devices.motor import Motor
from ...core.instrument.privileges import PRIV_BEAMSTOP
from ...core.services.interpreter import InterpreterError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ShutterBeamstop(ToolFrame):
    required_devices = ['xray_source', 'Motor_BeamStop_X', 'Motor_BeamStop_Y']

    def init_gui(self, *args, **kwargs):
        self.on_privlevel_changed(self.instrument.services['accounting'],
                                  self.instrument.services['accounting'].get_privilegelevel())
        self.on_motor_position_change(None, None)

    def on_privlevel_changed(self, accounting, newprivlevel):
        if not accounting.has_privilege(PRIV_BEAMSTOP):
            self.builder.get_object('beamstop_in_button').set_sensitive(False)
            self.builder.get_object('beamstop_out_button').set_sensitive(False)
        else:
            self.on_motor_position_change(None, None)

    def on_device_variable_change(self, device, varname, value):
        if device.name == self.instrument.get_device('xray_source').name:
            if varname == 'shutter':
                self.builder.get_object('shutter_switch').set_state(value)

    def on_motor_position_change(self, motor: Optional[Motor], pos: Optional[float]):
        if motor is None or pos is None:
            logger.debug('Faked motor position changed signal caught by ShutterFrame.')
        else:
            logger.debug(
                'Motor position changed signal caught by ShutterFrame. Motor: {}. Position: {}'.format(motor.name, pos))
            try:
                logger.debug('Stored motor position is {}'.format(motor.where()))
            except KeyError:
                logger.debug('Stored motor position not yet available.')
        try:
            if motor is not None:
                beamstopstate = self.instrument.get_beamstop_state(**{motor.name: pos})
            else:
                beamstopstate = self.instrument.get_beamstop_state()
            logger.debug('beamstopstate: {}'.format(beamstopstate))
        except KeyError:
            # can happen at program initialization, when the motor position has not yet been read.
            logger.debug('No beamstop state yet.')
            GLib.timeout_add(1000, lambda m=motor, p=pos: self.on_motor_position_change(m, p))
            return False
        if beamstopstate == 'in':
            self.builder.get_object('beamstopstate_image').set_from_icon_name('beamstop-in', Gtk.IconSize.BUTTON)
            self.builder.get_object('beamstop_in_button').set_sensitive(False)
            self.builder.get_object('beamstop_out_button').set_sensitive(True)
        elif beamstopstate == 'out':
            self.builder.get_object('beamstopstate_image').set_from_icon_name('beamstop-out', Gtk.IconSize.BUTTON)
            self.builder.get_object('beamstop_in_button').set_sensitive(True)
            self.builder.get_object('beamstop_out_button').set_sensitive(False)
        else:
            self.builder.get_object('beamstopstate_image').set_from_icon_name('beamstop-inconsistent',
                                                                              Gtk.IconSize.BUTTON)
            self.builder.get_object('beamstop_in_button').set_sensitive(True)
            self.builder.get_object('beamstop_out_button').set_sensitive(True)
        return False

    def on_shutter_switch_set_state(self, switch, value):
        self.instrument.get_device('genix').shutter(value)
        return True

    def on_beamstop_in(self, button):
        try:
            self.instrument.services['interpreter'].execute_command(Beamstop, ('in',))
        except InterpreterError:
            error_message(self.widget, 'Cannot move beamstop', 'Interpreter is busy')

    def on_beamstop_out(self, button):
        try:
            self.instrument.services['interpreter'].execute_command(Beamstop, ('out',))
        except InterpreterError:
            error_message(self.widget, 'Cannot move beamstop', 'Interpreter is busy')
