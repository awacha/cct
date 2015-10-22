from ..core.toolwindow import ToolWindow, error_message
import logging
logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class Scan(ToolWindow):
    def _init_gui(self, *args):
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


    def start_scan(self, button):
        if button.get_label()=='Start':
            self._make_insensitive('Scan sequence is running', ['close_button', 'entry_grid'])
            self._builder.get_object('start_button').set_label('Stop')
            try:
                motor=self._builder.get_object('motorselector').get_active_text()
                nsteps=self._builder.get_object('nsteps_spin').get_value_as_int()
                exptime=self._builder.get_object('countingtime_spin').get_value()
                comment=self._builder.get_object('comment_entry').get_text().replace('"','\\"')
                if not comment.strip():
                    error_message(self._window, 'Cannot start scan', 'Please give the details of this scan in the "Comment" field.')
                    self._make_sensitive()
                    self._builder.get_object('start_button').set_label('Start')
                if self._builder.get_object('symmetric_checkbutton').get_active():
                    width=self._builder.get_object('start_or_width_spin').get_value()
                    commandline='scanrel("%s", %f, %d, %f, "%s")'%(motor, width, nsteps, exptime, comment)
                else:
                    start=self._builder.get_object('start_or_width_spin').get_value()
                    end=self._builder.get_object('end_spin').get_value()
                    commandline='scan("%s", %f, %f, %d, %f, "%s")' %(motor, start, end, nsteps, exptime, comment)
                logger.debug('Would execute the following command: '+commandline)
            except:
                self._make_sensitive()
                self._builder.get_object('start_button').set_label('Start')
                raise
        elif button.get_label()=='Stop':
            self._make_sensitive()
            self._builder.get_object('start_button').set_label('Start')
        return True


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

