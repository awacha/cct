from gi.repository import GLib, Gtk

from ...core.dialogs import error_message
from ...core.toolwindow import ToolWindow
from ....core.devices import Motor
from ....core.instrument.privileges import PRIV_BEAMSTOP, PRIV_MOVEMOTORS, PRIV_PINHOLE


class MotorMover(ToolWindow):
    destroy_on_close = True
    privlevel = PRIV_MOVEMOTORS
    widgets_to_make_insensitive = ['close_button', 'motorselector', 'target_spin', 'relative_checkbutton']

    def __init__(self, gladefile, toplevelname, instrument, windowtitle, motorname, *args, **kwargs):
        self.motorname = motorname
        self.required_devices = ['Motor_' + motorname]
        super().__init__(gladefile, toplevelname, instrument, windowtitle, motorname, *args, **kwargs)

    def init_gui(self, motorname):
        motorselector = self.builder.get_object('motorselector')
        for i, m in enumerate(sorted(self.instrument.motors)):
            motorselector.append_text(m)
            if m == motorname:
                motorselector.set_active(i)
        motorselector.connect('changed', self.on_motorselector_changed)
        GLib.idle_add(lambda ms=motorselector: self.on_motorselector_changed(ms))

    def on_move(self, button):
        motor = self.instrument.motors[self.motorname]
        if button.get_label() == 'Move':
            if ((self.builder.get_object('motorselector').get_active_text() in ['BeamStop_X', 'BeamStop_Y']) and
                    not self.instrument.services['accounting'].has_privilege(PRIV_BEAMSTOP)):
                error_message(self.widget, 'Cannot move beamstop', 'Insufficient privileges')
                return
            if ((self.builder.get_object('motorselector').get_active_text() in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y',
                                                                                'PH3_X', 'PH3_Y']) and
                    not self.instrument.services['accounting'].has_privilege(PRIV_PINHOLE)):
                error_message(self.widget, 'Cannot move pinholes', 'Insufficient privileges')
                return
            self.builder.get_object('move_button').set_label('Stop')
            try:
                target = self.builder.get_object('target_spin').get_value()
                if self.builder.get_object('relative_checkbutton').get_active():
                    motor.moverel(target)
                else:
                    motor.moveto(target)
            except:
                button.set_label('Move')
                raise
            self.set_sensitive(False, 'Motor is moving', )
        else:
            motor.stop()

    def on_motor_position_change(self, motor: Motor, newposition: float):
        self.builder.get_object('currentpos_label').set_text('%.3f' % newposition)
        return False

    def on_motor_stop(self, motor, target_reached):
        self.builder.get_object('move_button').set_label('Move')
        self.set_sensitive(True)

    def on_device_error(self, motor, varname, exc, tb):
        if self.builder.get_object('move_button').get_label() == 'Stop':
            self.on_motor_stop(motor, False)
        error_message(self.widget, 'Motor error: ' + str(exc), tb)

    def on_motorselector_changed(self, combobox: Gtk.ComboBoxText):
        if self.widget.get_visible():
            self.motorname = combobox.get_active_text()
            self.required_devices = ['Motor_' + self.motorname]
            self.on_mainwidget_map(self.widget)  # for re-connecting the signal handlers
            self.builder.get_object('currentpos_label').set_text(
                '%.3f' % self.instrument.motors[self.motorname].where())
            self.adjust_limits()
        return False

    def adjust_limits(self):
        motor = self.instrument.motors[self.motorname]
        lims = motor.get_limits()
        where = motor.where()
        if self.builder.get_object('relative_checkbutton').get_active():
            lims = [l - where for l in lims]
            where = 0
        adj = self.builder.get_object('target_adjustment')
        adj.set_lower(lims[0])
        adj.set_upper(lims[1])
        adj.set_value(where)

    def on_relative_toggled(self, checkbutton):
        self.adjust_limits()
