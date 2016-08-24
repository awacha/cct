import datetime

from ..core.indicator import Indicator, IndicatorState
from ..core.toolwindow import ToolWindow


class HaakePhoenix(ToolWindow):
    required_devices = ['haakephoenix']

    def __init__(self, *args, **wargs):
        self.indicators = {}
        super().__init__(*args, **wargs)

    def init_gui(self, *args, **kwargs):
        statusgrid = self.builder.get_object('statusgrid')
        for row, column, vn, label in [(0, 0, '_status', 'Status'),
                                       (0, 1, 'setpoint', 'Target temperature'),
                                       (0, 2, 'temperature', 'Temperature'),
                                       (0, 3, 'pump_power', 'Pump speed'),
                                       (0, 4, 'control_on', 'Temperature control'),
                                       (1, 0, 'lowlimit', 'Low limit'),
                                       (1, 1, 'highlimit', 'High limit'),
                                       (1, 2, 'cooling_on', 'Cooling'),
                                       (1, 3, 'control_external', 'Control'),
                                       (1, 4, 'diffcontrol_on', 'Differential control')]:
            self.indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            statusgrid.attach(self.indicators[vn], column, row, 1, 1)
        errorgrid = self.builder.get_object('errorgrid')
        for row, column, vn, label in [(0, 0, 'external_pt100_error', 'External Pt100'),  #
                                       (0, 1, 'internal_pt100_error', 'Internal Pt100'),  #
                                       (0, 2, 'liquid_level_low_error', 'Liquid level'),  #
                                       (0, 3, 'liquid_level_alarm_error', 'Liquid level alarm'),  #
                                       (0, 4, 'cooling_error', 'Cooling system'),  #
                                       (1, 0, 'pump_overload_error', 'Pump'),  #
                                       (1, 1, 'external_alarm_error', 'External alarm'),  #
                                       (1, 2, 'overtemperature_error', 'Overtemperature'),  #
                                       (1, 3, 'main_relay_missing_error', 'Main relay'),  #
                                       (1, 4, 'faultstatus', 'Status flags')]:  #
            self.indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            errorgrid.attach(self.indicators[vn], column, row, 1, 1)
        othergrid = self.builder.get_object('othergrid')
        for row, column, vn, label in [(0, 0, 'firmwareversion', 'Firmware version'),  #
                                       (0, 1, 'date', 'Date'),  #
                                       (0, 2, 'time', 'Time'),  #
                                       (0, 3, 'autostart', 'Autostart'),  #
                                       (0, 4, 'beep', 'Beep'),  #
                                       (1, 0, 'fuzzyid', 'Fuzzy identification'),  #
                                       (1, 1, 'fuzzycontrol', 'Fuzzy control'),  #
                                       (1, 2, 'fuzzystatus', 'Fuzzy status'),  #
                                       (1, 3, 'watchdog_on', 'Watchdog'),  #
                                       (1, 4, 'watchdog_setpoint', 'Watchdog setpoint')]:  #
            self.indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            othergrid.attach(self.indicators[vn], column, row, 1, 1)
        self.update_indicators()

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self.update_indicators()

    def update_indicators(self):
        dev = self.instrument.get_device('haakephoenix')
        for vn in self.indicators:
            self.on_device_variable_change(dev, vn, dev.get_variable(vn))
        self.builder.get_object('setpoint_adjustment').set_value(
            dev.get_variable('setpoint'))
        self.builder.get_object('lowlimit_adjustment').set_value(
            dev.get_variable('lowlimit'))
        self.builder.get_object('highlimit_adjustment').set_value(
            dev.get_variable('highlimit'))

    def on_device_variable_change(self, device, variablename, newvalue):
        if variablename in ['_status', 'firmwareversion', 'fuzzycontrol', 'date', 'time', 'faultstatus']:
            self.indicators[variablename].set_value(str(newvalue), IndicatorState.NEUTRAL)
        elif variablename in ['setpoint', 'temperature_internal', 'lowlimit', 'highlimit']:
            self.indicators[variablename].set_value('%.2f°C' % newvalue, IndicatorState.NEUTRAL)
        elif variablename in ['control_on', 'cooling_on', 'diffcontrol_on', 'watchdog_on', 'beep', 'fuzzyid',
                              'fuzzystatus',
                              'autostart']:
            self.indicators[variablename].set_value(['OFF', 'ON'][int(bool(newvalue))],
                                                    [IndicatorState.ERROR, IndicatorState.OK][int(bool(newvalue))])
        elif variablename in ['pump_power']:
            self.indicators[variablename].set_value('%.2f %%' % newvalue,
                                                    [IndicatorState.ERROR, IndicatorState.OK][newvalue > 0])
        elif variablename in ['external_pt100_error', 'internal_pt100_error', 'liquid_level_low_error', 'cooling_error',
                              'main_relay_missing_error']:
            self.indicators[variablename].set_value(['OK', 'ERROR'][int(bool(newvalue))],
                                                    [IndicatorState.OK, IndicatorState.ERROR][int(bool(newvalue))])
        elif variablename in ['liquid_level_alarm_error', 'external_alarm_error', 'overtemperature_error']:
            self.indicators[variablename].set_value(['OK', 'ALARM'][int(bool(newvalue))],
                                                    [IndicatorState.OK, IndicatorState.ERROR][int(bool(newvalue))])
        elif variablename in ['pump_overload_error']:
            self.indicators[variablename].set_value(['OK', 'OVERLOAD'][int(bool(newvalue))],
                                                    [IndicatorState.OK, IndicatorState.ERROR][int(bool(newvalue))])
        elif variablename in ['watchdog_setpoint']:
            self.indicators[variablename].set_value('%.2f sec' % newvalue, IndicatorState.UNKNOWN)
        elif variablename in ['control_external']:
            self.indicators[variablename].set_value(['Internal', 'External'][int(bool(newvalue))],
                                                    IndicatorState.NEUTRAL)

        if variablename == 'fuzzyid':
            self.builder.get_object('fuzzyid_switch').set_state(bool(newvalue))
        elif variablename == 'pump_power':
            self.builder.get_object('circulator_switch').set_state(newvalue > 0)
        return False

    def on_circulator_switch_state_set(self, switch, state):
        dev = self.instrument.get_device('haakephoenix')
        if state:
            dev.execute_command('start')
        else:
            dev.execute_command('stop')
        return True

    def on_fuzzyid_switch_state_set(self, switch, state):
        self.instrument.get_device('haakephoenix').set_variable('fuzzyid', state)
        return True

    def on_set_setpoint(self, button):
        spinbutton = self.builder.get_object('setpoint_spin')
        self.instrument.get_device('haakephoenix').set_variable('setpoint', spinbutton.get_value())

    def on_set_lowlimit(self, button):
        spinbutton = self.builder.get_object('lowlimit_spin')
        self.instrument.get_device('haakephoenix').set_variable('lowlimit', spinbutton.get_value())

    def on_set_highlimit(self, button):
        spinbutton = self.builder.get_object('highlimit_spin')
        self.instrument.get_device('haakephoenix').set_variable('highlimit', spinbutton.get_value())

    def on_update_rtc(self, button):
        now = datetime.datetime.now()
        self.instrument.get_device('haakephoenix').set_variable('date', now.date())
        self.instrument.get_device('haakephoenix').set_variable('time', now.time())
