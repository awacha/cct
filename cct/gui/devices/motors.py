import logging

from gi.repository import Gtk, GLib

from ..core.toolwindow import ToolWindow, error_message, question_message
from ...core.devices.device import DeviceError
from ...core.instrument.privileges import PRIV_MOTORCONFIG, PRIV_MOTORCALIB, PRIV_BEAMSTOP, PRIV_PINHOLE

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Motors(ToolWindow):
    def _init_gui(self, *args):
        self._model=self._builder.get_object('motorlist')
        self._motorconnections=[]
        for m in sorted(self._instrument.motors):
            mot=self._instrument.motors[m]
            lims=mot.get_limits()
            self._model.append((m, '%.3f'%lims[0], '%.3f'%lims[1], '%.3f'%mot.where(), '%.3f'%mot.speed(), mot.leftlimitswitch(),
                                mot.rightlimitswitch(), '%d'%mot.load(), ', '.join(mot.decode_error_flags())))
            self._motorconnections.append((mot,mot.connect('variable-change', self.on_motor_variable_change, m)))
            self._motorconnections.append((mot, mot.connect('stop', self.on_motor_stop, m)))
        self.on_samplelist_changed(self._instrument.samplestore)
        self._check_beamstop_state()

    def on_motor_variable_change(self, motor, var, value, motorname):
        for row in self._model:
            if row[0]==motorname:
                if var=='softleft':
                    row[1]='%.3f'%value
                elif var=='softright':
                    row[2]='%.3f'%value
                elif var=='actualposition':
                    row[3]='%.3f'%value
                elif var=='actualspeed':
                    row[4]='%.3f'%value
                elif var=='leftswitchstatus':
                    row[5]=value
                elif var=='rightswitchstatus':
                    row[6]=value
                elif var=='load':
                    row[7]='%d'%value
                elif var=='drivererror':
                    row[8]=', '.join(motor.decode_error_flags(value))
        if var == 'actualposition' and motorname in ['BeamStop_X', 'BeamStop_Y']:
            self._check_beamstop_state()
        return False

    def on_motor_stop(self, motor, targetreached, motorname):
        if hasattr(self, '_movebeamstop'):
            if motorname == 'BeamStop_X':
                # moving the BeamStop_X just ended, move BeamStop_Y
                ypos = self._instrument.config['beamstop'][self._movebeamstop][1]
                GLib.idle_add(lambda yp=ypos: self._instrument.motors['BeamStop_Y'].moveto(yp) and False)
            elif motorname == 'BeamStop_Y':
                # moving motor BeamStopY is ended too, clean up.
                del self._movebeamstop
                self._make_sensitive()
        if hasattr(self, '_movetosample'):
            if motorname == 'Sample_X':
                # moving Sample_X ended. Move Sample_Y
                GLib.idle_add(lambda yp=self._movetosample.positiony.val: self._instrument.motors['Sample_Y'].moveto(
                    yp) and False)
            elif motorname == 'Sample_Y':
                del self._movetosample
                self._make_sensitive()

    def _check_beamstop_state(self):
        xpos = self._instrument.motors['BeamStop_X'].where()
        ypos = self._instrument.motors['BeamStop_Y'].where()
        if (abs(xpos - self._instrument.config['beamstop']['in'][0]) < 0.001 and
                    abs(ypos - self._instrument.config['beamstop']['in'][1]) < 0.001):
            self._builder.get_object('beamstopstatusimage').set_from_icon_name('beamstop-in', Gtk.IconSize.BUTTON)
            self._builder.get_object('beamstopstatuslabel').set_label('Beamstop is in the beam')
        elif (abs(xpos - self._instrument.config['beamstop']['out'][0]) < 0.001 and
                      abs(ypos - self._instrument.config['beamstop']['out'][1]) < 0.001):
            self._builder.get_object('beamstopstatusimage').set_from_icon_name('beamstop-out', Gtk.IconSize.BUTTON)
            self._builder.get_object('beamstopstatuslabel').set_label('Beamstop is out of the beam')
        else:
            self._builder.get_object('beamstopstatusimage').set_from_icon_name('beamstop-inconsistent',
                                                                               Gtk.IconSize.BUTTON)
            self._builder.get_object('beamstopstatuslabel').set_label('Beamstop position inconsistent')

    def on_calibratebeamstop_in(self, button):
        if not self._instrument.accounting.has_privilege(PRIV_MOTORCALIB):
            error_message(self._window, 'Cannot calibrate beamstop position', 'Insufficient privileges')
            return
        xpos = self._instrument.motors['BeamStop_X'].where()
        ypos = self._instrument.motors['BeamStop_Y'].where()
        if question_message(self._window, 'Calibrate beamstop in position',
                            'Do you really want to set the new "beamstop in" position to (%f, %f)?' % (xpos, ypos)):
            self._instrument.config['beamstop']['in'] = (xpos, ypos)
            self._check_beamstop_state()

    def on_calibratebeamstop_out(self, button):
        if not self._instrument.accounting.has_privilege(PRIV_MOTORCALIB):
            error_message(self._window, 'Cannot calibrate beamstop position', 'Insufficient privileges')
            return
        xpos = self._instrument.motors['BeamStop_X'].where()
        ypos = self._instrument.motors['BeamStop_Y'].where()
        if question_message(self._window, 'Calibrate beamstop out position',
                            'Do you really want to set the new "beamstop out" position to (%f, %f)?' % (xpos, ypos)):
            self._instrument.config['beamstop']['out'] = (xpos, ypos)
            self._check_beamstop_state()

    def on_movebeamstop_in(self, button):
        self.movebeamstop(False)

    def on_movebeamstop_out(self, button):
        self.movebeamstop(True)

    def movebeamstop(self, out):
        try:
            error_message(self._window, 'Cannot move beamstop', 'Already moving ' + self._movebeamstop)
            return True
        except AttributeError:
            # this happens when `self` does not have a '_movebeamstop' attribute, i.e. the beamstop is not moving.
            pass
        if not self._instrument.accounting.has_privilege(PRIV_BEAMSTOP):
            error_message(self._window, 'Cannot move beamstop', 'Insufficient privileges')
            return
        try:
            if out:
                self._movebeamstop = 'out'
                xpos, ypos = self._instrument.config['beamstop']['out']
            else:
                self._movebeamstop = 'in'
                xpos, ypos = self._instrument.config['beamstop']['in']
            self._make_insensitive('Beamstop is moving', ['highlevel_expander'])
            self._instrument.motors['BeamStop_X'].moveto(xpos)
        except Exception as exc:
            self._make_sensitive()
            del self._movebeamstop
            error_message(self._window, 'Cannot start move', str(exc.args[0]))

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        self.on_unmap(window)
        self._samplestore_connection = self._instrument.samplestore.connect('list-changed',
                                                                            self.on_samplelist_changed)

    def on_unmap(self, window):
        try:
            self._instrument.samplestore.disconnect(self._samplestore_connection)
            del self._samplestore_connection
        except AttributeError:
            pass

    def on_samplelist_changed(self, samplestore):
        sampleselector = self._builder.get_object('sampleselector')
        lastselected = sampleselector.get_active_text()
        if not lastselected:
            lastselected = samplestore.get_active_name()
        sampleselector.remove_all()
        for i, s in enumerate(sorted(samplestore)):
            sampleselector.append_text(s.title)
            if s.title == lastselected:
                sampleselector.set_active(i)

    def on_moveto_sample(self, button):
        try:
            error_message(self._window, 'Cannot move sample motors',
                          'Already in motion to sample ' + str(self._movetosample))
            return True
        except AttributeError:
            # This happens when `self` does not have a `_movetosample` attribute, i.e. we are not moving.
            pass
        self._movetosample = self._instrument.samplestore.get_sample(
            self._builder.get_object('sampleselector').get_active_text())
        self._make_insensitive('Moving sample', ['highlevel_expander'])
        self._instrument.motors['Sample_X'].moveto(self._movetosample.positionx.val)

    def on_motorview_row_activate(self, motorview, path, column):
        self.on_move(None)

    def on_move(self, button):
        model, treeiter=self._builder.get_object('motortreeview').get_selection().get_selected()
        motorname=model[treeiter][0]
        movewindow = MotorMover('devices_motors_move.glade', 'motormover', self._instrument, self._application,
                                'Move motor', motorname)
        movewindow._window.show_all()

    def on_config(self, button):
        model, treeiter=self._builder.get_object('motortreeview').get_selection().get_selected()
        motorname=model[treeiter][0]
        configwindow = MotorConfig('devices_motors_config.glade', 'motorconfig', self._instrument, self._application,
                                   'Configure motor', motorname)
        configwindow._window.show_all()

class MotorConfig(ToolWindow):
    def _init_gui(self, motorname):
        self._privlevel = PRIV_MOTORCONFIG
        self._hide_on_close=False
        self._motorname=motorname
        motor=self._instrument.motors[motorname]
        self._builder.get_object('frametitle').set_label('Configure motor %s (%s/#%d)'%(motorname,motor._controller._instancename,
                                                                                        motor._index))
        limits=motor.get_limits()
        self._builder.get_object('leftlimit_adjustment').set_value(motor.get_variable('softleft'))
        self._builder.get_object('rightlimit_adjustment').set_value(motor.get_variable('softright'))
        self._builder.get_object('calibration_adjustment').set_value(motor.where())
        self._builder.get_object('drivingcurrent_adjustment').set_upper(motor._controller._top_RMS_current)
        self._builder.get_object('drivingcurrent_adjustment').set_value(motor.get_variable('maxcurrent'))
        self._builder.get_object('standbycurrent_adjustment').set_upper(motor._controller._top_RMS_current)
        self._builder.get_object('standbycurrent_adjustment').set_value(motor.get_variable('standbycurrent'))
        self._builder.get_object('freewheelingdelay_adjustment').set_value(motor.get_variable('freewheelingdelay'))
        self._builder.get_object('leftswitchenable_checkbutton').set_active(motor.get_variable('leftswitchenable'))
        self._builder.get_object('rightswitchenable_checkbutton').set_active(motor.get_variable('rightswitchenable'))
        self._builder.get_object('rampdiv_adjustment').set_value(motor.get_variable('rampdivisor'))
        self._builder.get_object('pulsediv_adjustment').set_value(motor.get_variable('pulsedivisor'))
        self._builder.get_object('microstep_adjustment').set_value(motor._controller._max_microsteps)
        self._builder.get_object('microstep_adjustment').set_value(motor.get_variable('microstepresolution'))

    def on_apply(self, button):
        tobechanged={}
        motor=self._instrument.motors[self._motorname]
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
            widget=self._builder.get_object(widgetname)
            if widgetname.endswith('_adjustment'):
                newvalue=widget.get_value()
            elif widgetname.endswith('_checkbutton'):
                newvalue=widget.get_active()
            else:
                raise NotImplementedError(widgetname)
            oldvalue=motor.get_variable(variablename)
            if oldvalue != newvalue:
                tobechanged[variablename]=newvalue
        if tobechanged:
            md=Gtk.MessageDialog(parent=self._window, flags=Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                 type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
                                 message_format='Please confirm changes to motor %s'%self._motorname)
            md.format_secondary_markup('The following parameters will be changed. <b>ARE YOU REALLY SURE?</b>:\n'+'\n'.join('    '+variablename+' to '+str(tobechanged[variablename]) for variablename in sorted(tobechanged)))
            result=md.run()
            if result==Gtk.ResponseType.YES:
                if 'actualposition' in tobechanged:
                    logger.info('Calibrating motor %s to %f.'%(self._motorname, tobechanged['actualposition']))
                    try:
                        motor.calibrate(tobechanged['actualposition'])
                    except DeviceError as de:
                        error_message(self._window, 'Calibration failed',str(de))
                    del tobechanged['actualposition']
                for k in tobechanged:
                    motor.set_variable(k, tobechanged[k])
                if tobechanged:
                    logger.info('Updated motor parameters: %s' % ', '.join(k for k in sorted(tobechanged)))
            else:
                logger.debug('Change cancelled.')
            md.destroy()
        self._window.destroy()


class MotorMover(ToolWindow):
    def _init_gui(self, motorname):
        self._hide_on_close=False
        motorselector=self._builder.get_object('motorselector')
        for i,m in enumerate(sorted(self._instrument.motors)):
            motorselector.append_text(m)
            if m==motorname:
                motorselector.set_active(i)
        motorselector.connect('changed', self.on_motorselector_changed)
        GLib.idle_add(lambda ms=motorselector:self.on_motorselector_changed(ms))

    def _breakdown_motorconnection(self):
        if hasattr(self, '_motorconnection'):
            for c in self._motorconnection:
                self._motor.disconnect(c)
            del self._motorconnection
            del self._motor

    def _establish_motorconnection(self):
        self._breakdown_motorconnection()
        self._motor=self._instrument.motors[self._builder.get_object('motorselector').get_active_text()]
        self._motorconnection=[self._motor.connect('variable-change', self.on_motor_variable_change),
                               self._motor.connect('stop', self.on_motor_stop),
                               self._motor.connect('error', self.on_motor_error)]

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        self._establish_motorconnection()

    def on_unmap(self, window):
        self._breakdown_motorconnection()
        ToolWindow.on_unmap(self, window)

    def on_move(self, button):
        if button.get_label()=='Move':
            if ((self._builder.get_object('motorselector').get_active_text() in ['BeamStop_X', 'BeamStop_Y']) and
                    not self._instrument.accounting.has_privilege(PRIV_BEAMSTOP)):
                error_message(self._window, 'Cannot move beamstop', 'Insufficient privileges')
                return
            if ((self._builder.get_object('motorselector').get_active_text() in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y',
                                                                                 'PH3_X', 'PH3_Y']) and
                    not self._instrument.accounting.has_privilege(PRIV_PINHOLE)):
                error_message(self._window, 'Cannot move pinholes', 'Insufficient privileges')
                return
            self._builder.get_object('move_button').set_label('Stop')
            try:
                target=self._builder.get_object('target_spin').get_value()
                if self._builder.get_object('relative_checkbutton').get_active():
                    self._motor.moverel(target)
                else:
                    self._motor.moveto(target)
            except:
                button.set_label('Move')
                raise
            self._make_insensitive('Motor is moving', widgets=['close_button', 'motorselector', 'target_spin', 'relative_checkbutton'])
        else:
            self._motor.stop()

    def on_motor_variable_change(self, motor, var, value):
        if var=='actualposition':
            self._builder.get_object('currentpos_label').set_text('%.3f'%value)
        return False

    def on_motor_stop(self, motor, target_reached):
        self._builder.get_object('move_button').set_label('Move')
        self._make_sensitive()

    def on_motor_error(self, motor, varname, exc,tb):
        if self._builder.get_object('move_button').get_label()=='Stop':
            self.on_motor_stop(motor, False)
        error_message(self._window,'Motor error: '+str(exc),tb)

    def on_motorselector_changed(self, combobox):
        if self._window.get_visible():
            self._establish_motorconnection()
            self._builder.get_object('currentpos_label').set_text('%.3f'%self._motor.where())
            self.adjust_limits()
        return False

    def adjust_limits(self):
        lims=self._motor.get_limits()
        where=self._motor.where()
        if self._builder.get_object('relative_checkbutton').get_active():
            lims=[l-where for l in lims]
            where=0
        adj=self._builder.get_object('target_adjustment')
        adj.set_lower(lims[0])
        adj.set_upper(lims[1])
        adj.set_value(where)

    def on_relative_toggled(self, checkbutton):
        self.adjust_limits()

