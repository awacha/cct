import logging

from ..core.dialogs import question_message
from ..core.indicator import Indicator, IndicatorState
from ..core.toolwindow import ToolWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GeniX(ToolWindow):
    widgets_to_make_insensitive = ['operations_buttonbox', 'statusindicators', 'errorindicators']
    required_devices = ['genix']

    def __init__(self, *args, **kwargs):
        self._updating_buttons = False
        self.indicators = {}
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        statusindicators = self.builder.get_object('statusindicators')
        for row, column, vn, label in [(0, 0, '_status', 'Status'), (0, 1, 'ht', 'Tube voltage'),
                                       (0, 2, 'current', 'Tube current'), (0, 3, 'power', 'Power'),
                                       (0, 4, 'tubetime', 'Tube on-time'), (1, 0, 'remote_mode', 'Remote control'),
                                       (1, 1, 'xrays', 'X-ray generator'), (1, 2, 'shutter', 'Shutter'),
                                       (1, 3, 'interlock', 'Interlock'), (1, 4, 'overridden', 'Override mode')]:
            self.indicators[vn] = Indicator(label, 'N/A', IndicatorState.UNKNOWN)
            statusindicators.attach(self.indicators[vn], column, row, 1, 1)
        errorindicators = self.builder.get_object('errorindicators')
        for row, column, vn, label in [(0, 0, 'faults', 'Faults present'),
                                       (0, 1, 'xray_light_fault', 'X-rays on light'),
                                       (0, 2, 'shutter_light_fault', 'Shutter open light'),
                                       (0, 3, 'vacuum_fault', 'Optics vacuum'),
                                       (0, 4, 'waterflow_fault', 'Water cooling'),
                                       (1, 0, 'tube_position_fault', 'Tube in place'),
                                       (1, 1, 'filament_fault', 'Tube filament'),
                                       (1, 2, 'safety_shutter_fault', 'Safety shutter'),
                                       (1, 3, 'sensor1_fault', 'Sensor #1'),
                                       (1, 4, 'sensor2_fault', 'Sensor #2'),
                                       (2, 0, 'temperature_fault', 'Tube temperature'),
                                       (2, 1, 'relay_interlock_fault', 'Interlock relays'),
                                       (2, 2, 'door_fault', 'Interlock system'),
                                       (2, 3, 'tube_warmup_needed', 'Warm-up')]:
            self.indicators[vn] = Indicator(label, 'N/A', IndicatorState.UNKNOWN)
            errorindicators.attach(self.indicators[vn], column, row, 1, 1)
        self.update_indicators()
        self.set_powerbuttons_sensitivity()

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self.update_indicators()
        return False

    def update_indicators(self):
        genix = self.instrument.get_device('genix')
        for vn in self.indicators:
            self.on_device_variable_change(genix, vn, genix.get_variable(vn))
        genixshutter = genix.get_variable('shutter')
        shuttertoggle = self.builder.get_object('shutter_toggle').get_active()
        if genixshutter != shuttertoggle:
            self.builder.get_object('shutter_toggle').set_active(genix.get_variable('shutter'))
        genixxrays = genix.get_variable('xrays')
        xraystoggle = self.builder.get_object('xraystate_toggle').get_active()
        if genixxrays != xraystoggle:
            self.builder.get_object('xraystate_toggle').set_active(genix.get_variable('xrays'))
        self.builder.get_object('warmup_toggle').set_active(genix.get_variable('_status') == 'Warming up')

    def on_warmup(self, button):
        genix = self.instrument.get_device('genix')
        if self._updating_buttons:
            return
        if button.get_active():
            try:
                if genix.get_variable('_status') == 'Power off':
                    genix.start_warmup()
                else:
                    logger.error('Cannot start warm-up procedure unless the X-ray source is in "Power off" state.')
            except:
                button.set_active(False)
                raise
        else:
            if (not genix.get_variable('_status') == 'Warming up') or (
                    question_message(self.widget, 'Do you really want to break the warm-up sequence?',
                                     'Voltage will be gradually decreased to 0 kV.')):
                genix.stop_warmup()

    def on_resetfaults(self, button):
        self.instrument.get_device('genix').reset_faults()

    def on_poweroff(self, button):
        self.instrument.get_device('genix').set_power('off')

    def on_standby(self, button):
        self.instrument.get_device('genix').set_power('standby')

    def on_shutter(self, button):
        if self._updating_buttons:
            return
        genix = self.instrument.get_device('genix')
        logger.debug('Shutter button toggled to: ' + str(button.get_active()))
        if genix.get_variable('shutter') != button.get_active():
            genix.execute_command('shutter', button.get_active())

    def on_xraystate(self, button):
        if self._updating_buttons:
            return
        self.instrument.get_device('genix').set_xrays(button.get_active())

    def on_fullpower(self, button):
        self.instrument.get_device('genix').set_power('full')

    def set_powerbuttons_sensitivity(self, status=None):
        if status is None:
            status = self.instrument.get_device('genix').get_variable('_status')
        if self.instrument.get_device('genix').is_warmup_needed():
            self.builder.get_object('warmup_toggle').get_style_context().add_class('suggested-action')
            self.builder.get_object('standby_button').set_sensitive(False)
            self.builder.get_object('fullpower_button').set_sensitive(False)
        else:
            self.builder.get_object('warmup_toggle').get_style_context().remove_class('suggested-action')
            self.builder.get_object('xraystate_toggle').set_sensitive(status in ['Power off', 'X-rays off'])
            self.builder.get_object('shutter_toggle').set_sensitive(
                status in ['Power off', 'Powering down', 'Ramping up', 'Going to stand-by', 'Warming up', 'Low power',
                           'Full power'])
            self.builder.get_object('powerdown_button').set_sensitive(
                status in ['Ramping up', 'Low power', 'Full power']
            )
            self.builder.get_object('standby_button').set_sensitive(
                status in ['Power off', 'Full power']
            )
            self.builder.get_object('fullpower_button').set_sensitive(
                status in ['Low power']
            )
            self.builder.get_object('warmup_toggle').set_sensitive(
                status in ['Power off', 'Warming up']
            )
            if status not in ['Powering down']:
                self.builder.get_object('warmup_toggle').set_active(status == 'Warming up')

    def on_device_variable_change(self, genix, variablename, newvalue):
        logger.debug('GeniX on_variable_change')
        if variablename == '_status':
            self.indicators[variablename].set_value(newvalue, IndicatorState.NEUTRAL)
            try:
                self._updating_buttons = True
                if newvalue == 'Disconnected':
                    self.on_close(self.builder.get_object('close_button'), None)
                self.set_powerbuttons_sensitivity(newvalue)
            finally:
                self._updating_buttons = False
        elif variablename == 'ht':
            self.indicators[variablename].set_value('%.2f kV' % newvalue, IndicatorState.NEUTRAL)
        elif variablename == 'current':
            self.indicators[variablename].set_value('%.2f mA' % newvalue, IndicatorState.NEUTRAL)
        elif variablename == 'power':
            self.indicators[variablename].set_value('%.2f W' % newvalue, IndicatorState.NEUTRAL)
        elif variablename == 'tubetime':
            self.indicators[variablename].set_value('%.2f h / %.2f days' % (newvalue, newvalue / 24),
                                                    IndicatorState.NEUTRAL)
        elif variablename == 'remote_mode':
            self.indicators[variablename].set_value(['No', 'Yes'][newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][newvalue])
            self.set_sensitive(newvalue)
        elif variablename == 'xrays':
            self.indicators[variablename].set_value(['Off', 'On'][newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][newvalue])
            xraystate_toggle = self.builder.get_object('xraystate_toggle')
            if xraystate_toggle.get_active() != newvalue:
                xraystate_toggle.set_active(newvalue)
            if not newvalue:
                xraystate_toggle.set_sensitive(True)
        elif variablename == 'shutter':
            self.indicators[variablename].set_value(['Open', 'Closed'][not newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][not newvalue])
            shutter_toggle = self.builder.get_object('shutter_toggle')
            if shutter_toggle.get_active() != newvalue:
                shutter_toggle.set_active(newvalue)
        elif variablename == 'interlock':
            self.indicators[variablename].set_value(['Broken', 'Set'][newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][newvalue])
        elif variablename == 'overridden':
            self.indicators[variablename].set_value(['Active', 'No'][not newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][not newvalue])
        elif variablename == 'faults':
            self.builder.get_object('resetfaults_button').set_sensitive(newvalue)
            self.indicators[variablename].set_value(['Present', 'None'][not newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][not newvalue])
        elif variablename in ['xray_light_fault', 'shutter_light_fault', 'filament_fault', 'safety_shutter_fault',
                              'sensor1_fault', 'sensor2_fault', 'vacuum_fault', 'waterflow_fault',
                              'relay_interlock_fault', 'door_fault']:
            self.indicators[variablename].set_value(['Broken', 'Working'][not newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][not newvalue])
        elif variablename == 'tube_position_fault':
            self.indicators[variablename].set_value(['Missing', 'Yes'][not newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][not newvalue])
        elif variablename == 'temperature_fault':
            self.indicators[variablename].set_value(['Overheating', 'OK'][not newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][not newvalue])
        elif variablename == 'tube_warmup_needed':
            self.indicators[variablename].set_value(['Needed', 'Not needed'][not newvalue],
                                                    [IndicatorState.ERROR, IndicatorState.OK][not newvalue])
