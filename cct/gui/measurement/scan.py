import logging

from gi.repository import Gtk

from ..core.functions import update_comboboxtext_choices, notify
from ..core.scangraph import ScanGraph
from ..core.toolwindow import ToolWindow, error_message
from ...core.commands.motor import Moveto
from ...core.commands.scan import Scan, ScanRel
from ...core.commands.xray_source import Shutter
from ...core.devices import Motor
from ...core.services.exposureanalyzer import ExposureAnalyzer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ScanMeasurement(ToolWindow):
    required_devices = ['detector', 'xray_source']
    def __init__(self, *args, **kwargs):
        self._scanfsn = None
        self.scangraph = None
        self._exposureanalyzer_connections = []
        self.killed = False
        self._scan_arguments = ()
        self._scan_commandclass = None
        self._scan_commandline = ''
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        update_comboboxtext_choices(self.builder.get_object('motorselector'),
                                    sorted(self.instrument.motors))
        self.on_symmetric_scan_toggled(self.builder.get_object('symmetric_checkbutton'))

    # noinspection PyMethodMayBeStatic
    def on_motor_selected(self, comboboxtext):
        return False

    def recalculate_stepsize(self, widget):
        nsteps = self.builder.get_object('nsteps_spin').get_value_as_int()
        if self.builder.get_object('symmetric_checkbutton').get_active():
            end = self.builder.get_object('start_or_width_spin').get_value()
            start = -end
        else:
            start = self.builder.get_object('start_or_width_spin').get_value()
            end = self.builder.get_object('end_spin').get_value()
        self.builder.get_object('stepsize_label').set_text(str((end - start) / (nsteps - 1)))
        return False

    def start_scan(self, button):
        if button.get_label() == 'Stop':
            assert self._scanfsn is not None
            self.killed = True
            self.instrument.services['interpreter'].kill()
            return True
        assert button.get_label() == 'Start'
        assert self._scanfsn is None
        motor = self.instrument.motors[self.builder.get_object('motorselector').get_active_text()]
        assert isinstance(motor, Motor)
        self.killed = False
        nsteps = self.builder.get_object('nsteps_spin').get_value_as_int()
        exptime = self.builder.get_object('countingtime_spin').get_value()
        comment = self.builder.get_object('comment_entry').get_text().replace('"', '\\"')
        if not comment.strip():
            self.error_message('Please fill in the "Comment" field.')
            return True
        if self.builder.get_object('symmetric_checkbutton').get_active():
            width = self.builder.get_object('start_or_width_spin').get_value()
            where = motor.where()
            start = where - width
            end = where + width
            self._scan_arguments = (motor.name, width, nsteps, exptime, comment)
            self._scan_commandclass = ScanRel
            self._scan_commandline = 'scanrel("{}", {:f}, {:d}, {:f}, "{}")'.format(*self._scan_arguments)
        else:
            start = self.builder.get_object('start_or_width_spin').get_value()
            end = self.builder.get_object('end_spin').get_value()
            self._scan_arguments = (motor.name, start, end, nsteps, exptime, comment)
            self._scan_commandclass = Scan
            self._scan_commandline = 'scan("{}", {:f}, {:f}, {:d}, {:f}, "{}")'.format(*self._scan_arguments)
        if not (motor.checklimits(start) and motor.checklimits(end)):
            self.error_message('Start and end positions outside the limits of motor {}.'.format(motor.name))
            return True
        ea = self.instrument.services['exposureanalyzer']
        assert isinstance(ea, ExposureAnalyzer)
        self._exposureanalyzer_connections = [
            ea.connect('scanpoint', self.on_scanpoint),
            ea.connect('image', self.on_image)]
        self.builder.get_object('start_button').set_label('Stop')
        self.builder.get_object('start_button').get_image().set_from_icon_name('gtk-stop', Gtk.IconSize.BUTTON)
        self._scanfsn = self.instrument.services['filesequence'].get_nextfreescan(acquire=False)
        if self._scan_commandclass is ScanRel:
            # do not move to the start position now.
            self.on_command_return(self.instrument.services['interpreter'], Moveto.name, True)
        else:
            self.execute_command(Moveto, (motor.name, start), additional_widgets=['entry_grid'])
        return True

    def on_image(self, exposureanalyzer, prefix, fsn, image, params, mask):
        self.scangraph.new_image(image, params, mask)
        return False

    def on_command_return(self, interpreter, commandname, returnvalue):
        super().on_command_return(interpreter, commandname, returnvalue)
        if self.killed:
            if (self.builder.get_object('shutter_checkbutton').get_active() and
                    self.instrument.get_device('xray_source').get_variable('shutter')):
                # close the shutter
                self.execute_command(Shutter, (False,), True, additional_widgets=['entry_grid'])
            else:
                commandname = 'shutter'
                returnvalue = False

        if commandname == 'moveto':
            if not returnvalue:
                # positioning error
                error_message(self.widget, 'Error moving motor', 'Target position not reached.')
                return False
            # otherwise open the shutter if needed
            if self.builder.get_object('shutter_checkbutton').get_active():
                self.execute_command(Shutter, (True,), True, additional_widgets=['entry_grid'])
            else:
                commandname = 'shutter'
                returnvalue = True

        if commandname == 'shutter' and returnvalue:  # notice that we do not use 'elif' !
            # shutter opened, start the scan.
            self.execute_command(self._scan_commandclass, self._scan_arguments, additional_widgets=['entry_grid'])
            motor = self.builder.get_object('motorselector').get_active_text()
            nsteps = self.builder.get_object('nsteps_spin').get_value_as_int()
            self.scangraph = ScanGraph([motor] + self.instrument.config['scan']['columns'], nsteps,
                                       self._scanfsn, self._scan_arguments[-1], self.instrument)
            self.scangraph.show_all()

        if commandname == 'scan' or commandname == 'scanrel':
            # scan finished. Close the shutter if needed.
            if self.builder.get_object('shutter_checkbutton').get_active():
                self.execute_command(Shutter, (False,), True, additional_widgets=['entry_grid'])
            else:
                commandname = 'shutter'
                returnvalue = False

        if commandname == 'shutter' and not returnvalue:
            # wait for the last scanpoint to arrive before calling finalize_scan()
            self.finalize_scan(killed=self.killed)

    def finalize_scan(self, killed: bool):
        if killed:
            self.info_message('Scan measurement stopped by user.')
        assert self._scanfsn is not None
        logger.debug('Finalizing scan')
        try:
            self.scangraph.truncate_scan()
            notify('Scan ended', 'Scan {:d} ended'.format(self._scanfsn))
        except AttributeError:
            pass
        self.scangraph = None
        self.builder.get_object('start_button').set_label('Start')
        self.builder.get_object('start_button').get_image().set_from_icon_name('system-run', Gtk.IconSize.BUTTON)
        self.builder.get_object('scan_progress').set_visible(False)
        for eac in self._exposureanalyzer_connections:
            self.instrument.services['exposureanalyzer'].disconnect(eac)
        self._exposureanalyzer_connections = []
        self._scanfsn = None


    def on_command_message(self, interpreter, commandname, message):
        logger.debug('Scan message: ' + message)

    def on_command_pulse(self, interpreter, commandname, message):
        progress = self.builder.get_object('scan_progress')
        progress.set_visible(True)
        progress.set_text(message)
        progress.pulse()

    def on_command_progress(self, interpreter, commandname, message, fraction):
        progress = self.builder.get_object('scan_progress')
        progress.set_visible(True)
        progress.set_fraction(fraction)
        progress.set_text(message)

    def on_scanpoint(self, exposureanalyzer, prefix, fsn, position, scandata):
        self.scangraph.append_data(scandata)

    def on_symmetric_scan_toggled(self, checkbutton):
        if checkbutton.get_active():
            self.builder.get_object('start_or_width_label').set_text('Half width:')
            self.builder.get_object('end_label').hide()
            self.builder.get_object('end_spin').hide()
        else:
            self.builder.get_object('start_or_width_label').set_text('Start:')
            self.builder.get_object('end_label').show()
            self.builder.get_object('end_spin').show()
        self.recalculate_stepsize(checkbutton)
        return False
