from gi.repository import Gtk
from ..core.toolwindow import ToolWindow

class Scan(ToolWindow):
    def _init_gui(self):
        combo=self._builder.get_object('motorselector')
        for m in sorted(self._instrument.motors):
            combo.append_text(m)
        combo.set_active(0)
        self.on_symmetric_scan_toggled(self._builder.get_object('symmetric_checkbutton'))

    def on_motor_selected(self, comboboxtext):
        #ToDo: later on it would be nice if the validation of the motor limits would be ensured even as the lower and upper limits of the spin buttons.
        return False

    def recalculate_stepsize(self, widget):
        nsteps=self._builder.get_object('nsteps_spin').get_value_as_int()
        if self._builder.get_object('symmetric_checkbutton').get_active():
            start=-self._builder.get_object('start_or_width_spin').get_value()
            end=-start
        else:
            start=self._builder.get_object('start_or_width_spin').get_value()
            end=self._builder.get_object('end_spin').get_value()
        self._builder.get_object('stepsize_label').set_text(str((end-start)/(nsteps-1)))
        return False

    def _make_insensitive(self):
        self.inhibit_close('Scan sequence is running')
        self._builder.get_object('dataentry_grid').set_sensitive(False)
        self._builder.get_object('close_button').set_sensitive(False)
        self._window.set_deletable(False)

    def _make_sensitive(self):
        self.permit_close()
        self._builder.get_object('dataentry_grid').set_sensitive(True)
        self._builder.get_object('close_button').set_sensitive(True)
        self._window.set_deletable(True)

    def start_scan(self, button):
        if button.get_label()=='Start':
            self._make_insensitive()
            motor=self._builder.get_object('motorselector').get_active_text()
            start=self._builder.get_object('start_spin').get_value()
            end=self._builder.get_object('end_spin').get_value()
            nsteps=self._builder.get_object('nsteps_spin').get_value_as_int()
            exptime=self._builder.get_object('countingtime_spin').get_value()
            comment=self._builder.get_object('comment_entry').get_text().replace('"','\\"')
            commandline='scan("%s", %f, %f, %d, %f, "%s")' %(motor, start, end, nsteps, exptime, comment)

            self.inhibit_close('Scan sequence is running')
            self._builder.get_object('dataentry_grid').set_sensitive(False)
            self._builder.get_object('close_button').set_sensitive(False)
            self._window.set_deletable(False)



    def on_symmetric_scan_toggled(self, checkbutton):
        if checkbutton.get_active():
            self._builder.get_object('start_or_width_label').set_text('Half width:')
            self._builder.get_object('end_label').hide()
            self._builder.get_object('end_spin').hide()
        else:
            self._builder.get_object('start_or_width_label').set_text('Start:')
            self._builder.get_object('end_label').show()
            self._builder.get_object('end_spin').show()
        self.recalculate_stepsize(checkbutton)
        return False
