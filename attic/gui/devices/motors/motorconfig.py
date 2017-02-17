import logging

from gi.repository import Gtk

from ...core.dialogs import error_message
from ...core.toolwindow import ToolWindow
from ....core.devices import Motor, TMCMCard, DeviceError
from ....core.instrument.privileges import PRIV_MOTORCONFIG

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MotorConfig(ToolWindow):
    privlevel = PRIV_MOTORCONFIG
    destroy_on_close = True

    def __init__(self, gladefile, toplevelname, instrument, windowtitle, motorname, *args, **kwargs):
        self.motorname = motorname
        self.required_devices = ['Motor_' + motorname]
        self._calibration_changed = False
        super().__init__(gladefile, toplevelname, instrument, windowtitle, motorname, *args, **kwargs)

    def init_gui(self, motorname):
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

    def on_calibration_changed(self, spinbutton):
        self._calibration_changed = True

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
            if widgetname == 'calibration_adjustment' and not self._calibration_changed:
                # it can happen that the motor moves while this dialog is open. With this check we avoid unintended
                # motor position calibration.
                continue
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
                    else:
                        self._calibration_changed = False
                    del tobechanged['actualposition']
                for k in tobechanged:
                    motor.set_variable(k, tobechanged[k])
                if tobechanged:
                    logger.info('Updated motor parameters: %s' % ', '.join(k for k in sorted(tobechanged)))
            else:
                logger.debug('Change cancelled.')
            md.destroy()
        self.widget.destroy()
