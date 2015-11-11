from ..core.indicator import Indicator, IndicatorState
from ..core.toolwindow import ToolWindow


class HaakePhoenix(ToolWindow):
    def _init_gui(self, *args):
        self._indicators = {}
        statusgrid = self._builder.get_object('statusgrid')
        for row, column, vn, label in [(0, 0, '_status', 'Status'),
                                       (0, 1, 'setpoint', 'Target temperature'),
                                       (0, 2, 'temperature_internal', 'Temperature'),
                                       (0, 3, 'pump_power', 'Pump speed'),
                                       (0, 4, 'control_on', 'Temperature control'),
                                       (1, 0, 'lowlimit', 'Low limit'),
                                       (1, 1, 'highlimit', 'High limit'),
                                       (1, 2, 'cooling_on', 'Cooling'),
                                       (1, 3, 'control_external', 'Control'),
                                       (1, 4, 'diffcontrol_on', 'Differential control')]:
            self._indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            statusgrid.attach(self._indicators[vn], row, column, 1, 1)
        errorgrid = self._builder.get_object('errorgrid')
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
            self._indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            errorgrid.attach(self._indicators[vn], row, column, 1, 1)
        othergrid = self._builder.get_object('othergrid')
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
            self._indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            othergrid.attach(self._indicators[vn], row, column, 1, 1)
        self._haakephoenix = self._instrument.devices['haakephoenix']

    def on_map(self, window):
        for vn in self._indicators:
            self.on_variable_change(self._haakephoenix, vn, self._haakephoenix.get_variable(vn))
        if not hasattr(self, '_haakephoenixconnections'):
            self._haakephoenixconnections = [self._haakephoenix.connect('variable-change', self.on_variable_change),
                                             ]

    def on_unmap(self, window):
        try:
            for c in self._haakephoenixconnections:
                self._haakephoenix.disconnect(c)
            del self._haakephoenixconnections
        except AttributeError:
            pass

    def on_variable_change(self, haakephoenix, varname, value):
        if varname in ['_status', 'firmwareversion', 'fuzzycontrol', 'date', 'time', 'faultstatus']:
            self._indicators[varname].set_value(str(value), IndicatorState.NEUTRAL)
        elif varname in ['setpoint', 'temperature_internal', 'lowlimit', 'highlimit']:
            self._indicators[varname].set_value('%.2f°C' % value, IndicatorState.NEUTRAL)
        elif varname in ['control_on', 'cooling_on', 'diffcontrol_on', 'watchdog_on', 'beep', 'fuzzyid', 'fuzzystatus',
                         'autostart']:
            self._indicators[varname].set_value(['OFF', 'ON'][int(bool(value))],
                                                [IndicatorState.ERROR, IndicatorState.OK][int(bool(value))])
        elif varname in ['pump_power']:
            self._indicators[varname].set_value('%.2f %%', [IndicatorState.ERROR, IndicatorState.OK][value > 0])
        elif varname in ['external_pt100_error', 'internal_pt100_error', 'liquid_level_low_error', 'cooling_error',
                         'main_relay_missing_error']:
            self._indicators[varname].set_value(['OK', 'ERROR'][int(bool(value))],
                                                [IndicatorState.OK, IndicatorState.ERROR][int(bool(value))])
        elif varname in ['liquid_level_alarm_error', 'external_alarm_error', 'overtemperature_error']:
            self._indicators[varname].set_value(['OK', 'ALARM'][int(bool(value))],
                                                [IndicatorState.OK, IndicatorState.ERROR][int(bool(value))])
        elif varname in ['pump_overload_error']:
            self._indicators[varname].set_value(['OK', 'OVERLOAD'][int(bool(value))],
                                                [IndicatorState.OK, IndicatorState.ERROR][int(bool(value))])
        elif varname in ['watchdog_setpoint']:
            self._indicators[varname].set_value('%.2f sec' % value, IndicatorState.UNKNOWN)
