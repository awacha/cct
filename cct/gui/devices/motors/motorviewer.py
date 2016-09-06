from gi.repository import GLib, Gtk

from .motorconfig import MotorConfig
from .motormover import MotorMover
from ...core.dialogs import error_message, question_message
from ...core.toolwindow import ToolWindow
from ....core.devices import Motor
from ....core.instrument.privileges import PRIV_MOTORCALIB, PRIV_BEAMSTOP


class Motors(ToolWindow):
    widgets_to_make_insensitive = ['highlevel_expander']
    required_devices = ['tmcm351a', 'tmcm351b', 'tmcm6110']

    def __init__(self, gladefile, toplevelname, instrument, windowtitle, *args, **kwargs):
        self._samplestore_connection = None
        self._movebeamstop = None
        self._movetosample = None
        self.required_devices = self.required_devices + ['Motor_' + m for m in instrument.motors]
        super().__init__(gladefile, toplevelname, instrument, windowtitle, *args, **kwargs)

    def init_gui(self, *args, **kwargs):
        model = self.builder.get_object('motorlist')
        for m in sorted(self.instrument.motors):
            mot = self.instrument.motors[m]
            assert isinstance(mot, Motor)
            lims = mot.get_limits()
            model.append((m, '%.3f' % lims[0], '%.3f' % lims[1], '%.3f' % mot.where(), '%.3f' % mot.speed(),
                          mot.leftlimitswitch(),
                          mot.rightlimitswitch(), '%d' % mot.load(), ', '.join(mot.decode_error_flags())))
        self.on_samplelist_changed(self.instrument.services['samplestore'])
        self.check_beamstop_state()

    def on_device_variable_change(self, motor: Motor, var: str, value: object):
        model = self.builder.get_object('motorlist')
        for row in model:
            if row[0] == motor.name:
                if var == 'softleft':
                    row[1] = '%.3f' % value
                elif var == 'softright':
                    row[2] = '%.3f' % value
                elif var == 'actualposition':
                    row[3] = '%.3f' % value
                elif var == 'actualspeed':
                    row[4] = '%.3f' % value
                elif var == 'leftswitchstatus':
                    row[5] = value
                elif var == 'rightswitchstatus':
                    row[6] = value
                elif var == 'load':
                    row[7] = '%d' % value
                elif var == 'drivererror':
                    row[8] = ', '.join(motor.decode_error_flags(value))
        if var == 'actualposition' and motor.name in ['BeamStop_X', 'BeamStop_Y']:
            self.check_beamstop_state()
        return False

    def on_motor_stop(self, motor: Motor, targetreached: bool):
        if self._movebeamstop is not None:
            if motor.name == 'BeamStop_X':
                # moving the BeamStop_X just ended, move BeamStop_Y
                ypos = self.instrument.config['beamstop'][self._movebeamstop][1]
                GLib.idle_add(lambda yp=ypos: self.instrument.motors['BeamStop_Y'].moveto(yp) and False)
            elif motor.name == 'BeamStop_Y':
                # moving motor BeamStopY is ended too, clean up.
                self._movebeamstop = None
                self.set_sensitive(True)
        if self._movetosample is not None:
            if motor.name == 'Sample_X':
                # moving Sample_X ended. Move Sample_Y
                GLib.idle_add(lambda yp=self._movetosample.positiony.val: self.instrument.motors['Sample_Y'].moveto(
                    yp) and False)
            elif motor.name == 'Sample_Y':
                self._movetosample = None
                self.set_sensitive(True)

    def check_beamstop_state(self):
        bss = self.instrument.get_beamstop_state()
        if bss == 'in':
            self.builder.get_object('beamstopstatusimage').set_from_icon_name('beamstop-in', Gtk.IconSize.BUTTON)
            self.builder.get_object('beamstopstatuslabel').set_label('Beamstop is in the beam')
        elif bss == 'out':
            self.builder.get_object('beamstopstatusimage').set_from_icon_name('beamstop-out', Gtk.IconSize.BUTTON)
            self.builder.get_object('beamstopstatuslabel').set_label('Beamstop is out of the beam')
        else:
            assert bss == 'unknown'
            self.builder.get_object('beamstopstatusimage').set_from_icon_name('beamstop-inconsistent',
                                                                              Gtk.IconSize.BUTTON)
            self.builder.get_object('beamstopstatuslabel').set_label('Beamstop position inconsistent')

    def on_calibratebeamstop_in(self, button):
        return self.calibratebeamstop('in')

    def on_calibratebeamstop_out(self, button):
        return self.calibratebeamstop('out')

    def calibratebeamstop(self, where: str):
        if where not in ['in', 'out']:
            raise ValueError(where)
        if not self.instrument.services['accounting'].has_privilege(PRIV_MOTORCALIB):
            error_message(self.widget, 'Cannot calibrate beamstop position', 'Insufficient privileges')
            return
        xpos = self.instrument.motors['BeamStop_X'].where()
        ypos = self.instrument.motors['BeamStop_Y'].where()
        if question_message(self.widget, 'Calibrate beamstop {} position'.format(where),
                            'Do you really want to set the new "beamstop {}" position to ({:f}, {:f})?'.format(where,
                                                                                                               xpos,
                                                                                                               ypos)):
            self.instrument.config['beamstop'][where] = (xpos, ypos)
            self.instrument.save_state()
            self.check_beamstop_state()

    def on_movebeamstop_in(self, button):
        self.movebeamstop(False)

    def on_movebeamstop_out(self, button):
        self.movebeamstop(True)

    def movebeamstop(self, out):
        if self._movebeamstop is not None:
            error_message(self.widget, 'Cannot move beamstop', 'Already moving ' + self._movebeamstop)
            return True
        if not self.instrument.services['accounting'].has_privilege(PRIV_BEAMSTOP):
            error_message(self.widget, 'Cannot move beamstop', 'Insufficient privileges')
            return
        try:
            if out:
                self._movebeamstop = 'out'
                xpos, ypos = self.instrument.config['beamstop']['out']
            else:
                self._movebeamstop = 'in'
                xpos, ypos = self.instrument.config['beamstop']['in']
            self.set_sensitive(False, 'Beamstop is moving')
            self.instrument.motors['BeamStop_X'].moveto(xpos)
        except Exception as exc:
            self.set_sensitive(True)
            self._movebeamstop = None
            error_message(self.widget, 'Cannot start move', str(exc.args[0]))

    def on_mainwidget_map(self, window):
        if ToolWindow.on_mainwidget_map(self, window):
            return True
        self._samplestore_connection = self.instrument.services['samplestore'].connect('list-changed',
                                                                                       self.on_samplelist_changed)
        return False

    def cleanup(self):
        if self._samplestore_connection is not None:
            self.instrument.services['samplestore'].disconnect(self._samplestore_connection)
            self._samplestore_connection = None
        super().cleanup()

    def on_samplelist_changed(self, samplestore):
        sampleselector = self.builder.get_object('sampleselector')
        lastselected = sampleselector.get_active_text()
        if not lastselected:
            lastselected = samplestore.get_active_name()
        sampleselector.remove_all()
        for i, s in enumerate(sorted(samplestore)):
            sampleselector.append_text(s.title)
            if s.title == lastselected:
                sampleselector.set_active(i)

    def on_moveto_sample(self, button):
        if self._movetosample is not None:
            error_message(self.widget, 'Cannot move sample motors',
                          'Already in motion to sample ' + str(self._movetosample))
            return True
        self._movetosample = self.instrument.services['samplestore'].get_sample(
            self.builder.get_object('sampleselector').get_active_text())
        self.set_sensitive(False, 'Moving sample')
        self.instrument.motors['Sample_X'].moveto(self._movetosample.positionx.val)

    def on_motorview_row_activate(self, motorview, path, column):
        self.on_move(None)

    def on_move(self, button):
        model, treeiter = self.builder.get_object('motortreeview').get_selection().get_selected()
        motorname = model[treeiter][0]
        movewindow = MotorMover('devices_motors_move.glade', 'motormover', self.instrument,
                                'Move motor', motorname)
        movewindow.show_all()

    def on_config(self, button):
        model, treeiter = self.builder.get_object('motortreeview').get_selection().get_selected()
        motorname = model[treeiter][0]
        configwindow = MotorConfig('devices_motors_config.glade', 'motorconfig', self.instrument,
                                   'Configure motor', motorname)
        configwindow.show_all()
