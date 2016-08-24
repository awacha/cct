import logging

from gi.repository import Gtk, GLib

from ..core.dialogs import error_message, question_message
from ..core.toolwindow import ToolWindow
from ...core.devices import DeviceError, Motor, TMCMCard
from ...core.instrument.privileges import PRIV_MOTORCONFIG, PRIV_MOTORCALIB, PRIV_BEAMSTOP, PRIV_PINHOLE, \
    PRIV_MOVEMOTORS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Motors(ToolWindow):
    widgets_to_make_insensitive = ['highlevel_expander']

    def __init__(self, *args, **kwargs):
        self._samplestore_connection = None
        self._movebeamstop = None
        self._movetosample = None
        super().__init__(*args, **kwargs)
        self.required_devices = ['Motor_' + m for m in self.instrument.motors]

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
        xpos = self.instrument.motors['BeamStop_X'].where()
        ypos = self.instrument.motors['BeamStop_Y'].where()
        if (abs(xpos - self.instrument.config['beamstop']['in'][0]) < 0.001 and
                    abs(ypos - self.instrument.config['beamstop']['in'][1]) < 0.001):
            self.builder.get_object('beamstopstatusimage').set_from_icon_name('beamstop-in', Gtk.IconSize.BUTTON)
            self.builder.get_object('beamstopstatuslabel').set_label('Beamstop is in the beam')
        elif (abs(xpos - self.instrument.config['beamstop']['out'][0]) < 0.001 and
                      abs(ypos - self.instrument.config['beamstop']['out'][1]) < 0.001):
            self.builder.get_object('beamstopstatusimage').set_from_icon_name('beamstop-out', Gtk.IconSize.BUTTON)
            self.builder.get_object('beamstopstatuslabel').set_label('Beamstop is out of the beam')
        else:
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


class MotorConfig(ToolWindow):
    privlevel = PRIV_MOTORCONFIG
    destroy_on_close = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.motorname = None

    def init_gui(self, motorname):
        self.motorname = motorname
        motor = self.instrument.motors[motorname]
        assert isinstance(motor.controller, TMCMCard)
        assert isinstance(motor, Motor)
        self.builder.get_object('frametitle').set_label(
            'Configure motor %s (%s/#%d)' % (motorname, motor.controller.name, motor.index))
        self.builder.get_object('leftlimit_adjustment').set_value(motor.get_variable('softleft'))
        self.builder.get_object('rightlimit_adjustment').set_value(motor.get_variable('softright'))
        self.builder.get_object('calibration_adjustment').set_value(motor.where())
        self.builder.get_object('drivingcurrent_adjustment').set_upper(motor.controller.top_RMS_current)
        self.builder.get_object('drivingcurrent_adjustment').set_value(motor.get_variable('maxcurrent'))
        self.builder.get_object('standbycurrent_adjustment').set_upper(motor.controller.top_RMS_current)
        self.builder.get_object('standbycurrent_adjustment').set_value(motor.get_variable('standbycurrent'))
        self.builder.get_object('freewheelingdelay_adjustment').set_value(motor.get_variable('freewheelingdelay'))
        self.builder.get_object('leftswitchenable_checkbutton').set_active(motor.get_variable('leftswitchenable'))
        self.builder.get_object('rightswitchenable_checkbutton').set_active(motor.get_variable('rightswitchenable'))
        self.builder.get_object('rampdiv_adjustment').set_value(motor.get_variable('rampdivisor'))
        self.builder.get_object('pulsediv_adjustment').set_value(motor.get_variable('pulsedivisor'))
        self.builder.get_object('microstep_adjustment').set_value(motor.controller.max_microsteps)
        self.builder.get_object('microstep_adjustment').set_value(motor.get_variable('microstepresolution'))

    def on_apply(self, button):
        tobechanged = {}
        motor = self.instrument.motors[self.motorname]
        for widgetname, variablename in [('leftlimit_adjustment', 'softleft'),
                                         ('rightlimit_adjustment', 'softright'),
                                         ('drivingcurrent_adjustment', 'maxcurrent'),
                                         ('standbycurrent_adjustment', 'standbycurrent'),
                                         ('freewheelingdelay_adjustment', 'freewheelingdelay'),
                                         ('leftswitchenable_checkbutton', 'leftswitchenable'),
                                         ('rightswitchenable_checkbutton', 'rightswitchenable'),
                                         ('rampdiv_adjustment', 'rampdivisor'),
                                         ('pulsediv_adjustment', 'pulsedivisor'),
                                         ('microstep_adjustment', 'microstepresolution'),
                                         ('calibration_adjustment', 'actualposition')]:
            widget = self.builder.get_object(widgetname)
            if widgetname.endswith('_adjustment'):
                newvalue = widget.get_value()
            elif widgetname.endswith('_checkbutton'):
                newvalue = widget.get_active()
            else:
                raise ValueError(widgetname)
            oldvalue = motor.get_variable(variablename)
            if oldvalue != newvalue:
                tobechanged[variablename] = newvalue
        if tobechanged:
            md = Gtk.MessageDialog(parent=self.widget,
                                   flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                   type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
                                   message_format='Please confirm changes to motor %s' % self.motorname)
            md.format_secondary_markup(
                'The following parameters will be changed. <b>ARE YOU REALLY SURE?</b>:\n' + '\n'.join(
                    '    ' + variablename + ' to ' + str(tobechanged[variablename]) for variablename in
                    sorted(tobechanged)))
            result = md.run()
            if result == Gtk.ResponseType.YES:
                if 'actualposition' in tobechanged:
                    logger.info('Calibrating motor %s to %f.' % (self.motorname, tobechanged['actualposition']))
                    try:
                        motor.calibrate(tobechanged['actualposition'])
                    except DeviceError as de:
                        error_message(self.widget, 'Calibration failed', str(de))
                    del tobechanged['actualposition']
                for k in tobechanged:
                    motor.set_variable(k, tobechanged[k])
                if tobechanged:
                    logger.info('Updated motor parameters: %s' % ', '.join(k for k in sorted(tobechanged)))
            else:
                logger.debug('Change cancelled.')
            md.destroy()
        self.widget.destroy()


class MotorMover(ToolWindow):
    destroy_on_close = True
    privlevel = PRIV_MOVEMOTORS
    widgets_to_make_insensitive = ['close_button', 'motorselector', 'target_spin', 'relative_checkbutton']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.motorname = None

    def init_gui(self, motorname):
        self.motorname = motorname
        self.required_devices = ['Motor_' + motorname]
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
            self.on_mainwidget_map(self.widget)  # for re-connecting the signal handlers
            self.motorname = combobox.get_active_text()
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
