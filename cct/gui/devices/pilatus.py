from ..core.indicator import Indicator, IndicatorState
from ..core.toolwindow import ToolWindow


class Pilatus(ToolWindow):
    def _init_gui(self, *args):
        self._indicators = {}
        grid = self._builder.get_object('constants_grid')
        for row, column, vn, label in [(0, 0, '_status', 'Camera state'),
                                       (0, 1, 'cameraname', 'Camera name'),
                                       (0, 2, 'cameraSN', 'Serial number'),
                                       (0, 3, 'version', 'Camserver version'),
                                       (0, 4, 'cameradef', 'Camera definition'),
                                       (0, 5, 'wpix', 'Image size')]:
            self._indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            grid.attach(self._indicators[vn], column, row, 1, 1)
        grid = self._builder.get_object('lowlevel_grid')
        for row, column, vn, label in [(0, 0, 'masterPID', 'Master PID'),
                                       (0, 1, 'controllingPID', 'Controlling PID'),
                                       (0, 2, 'pid', 'PID'),
                                       (0, 3, 'sel_bank', 'Selected bank'),
                                       (0, 4, 'sel_module', 'Selected module'),
                                       (0, 5, 'sel_chip', 'Selected chip'),
                                       (1, 0, 'imgmode', 'Image mode'),
                                       (1, 1, 'shutterstate', 'Shutter state'),
                                       (1, 2, 'imgpath', 'Image path'),
                                       (1, 3, 'lastimage', 'Last image'),
                                       (1, 4, 'lastcompletedimage', 'Last completed image'),
                                       (1, 5, 'diskfree', 'Free disk space')]:
            self._indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            grid.attach(self._indicators[vn], column, row, 1, 1)
        grid = self._builder.get_object('highlevel_grid')
        for row, column, vn, label in [(0, 0, 'exptime', 'Exposure time'),
                                       (0, 1, 'expperiod', 'Exposure period'),
                                       (0, 2, 'nimages', 'Number of images'),
                                       (0, 3, 'starttime', 'Start time'),
                                       (0, 4, 'timeleft', 'Time left'),
                                       (0, 5, 'targetfile', 'Target file'),
                                       (1, 0, 'threshold', 'Threshold'),
                                       (1, 1, 'gain', 'Gain'),
                                       (1, 2, 'vcmp', 'Vcmp'),
                                       (1, 3, 'trimfile', 'Trim file'),
                                       (1, 4, 'tau', 'Tau'),
                                       (1, 5, 'cutoff', 'Cutoff'), ]:
            self._indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            grid.attach(self._indicators[vn], column, row, 1, 1)
        grid = self._builder.get_object('ambient_grid')
        for row, column, vn, label in [(0, 0, 'temperature0', 'Power board temp.'),
                                       (0, 1, 'temperature1', 'Base plate temp.'),
                                       (0, 2, 'temperature2', 'Sensor temp.'),
                                       (0, 3, 'humidity0', 'Power board humidity'),
                                       (0, 4, 'humidity1', 'Base plate humidity'),
                                       (0, 5, 'humidity2', 'Sensor humidity')]:
            self._indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            grid.attach(self._indicators[vn], column, row, 1, 1)
        self._update_indicators()

    def _cleanup_signalconnections(self):
        try:
            self._instrument.devices['pilatus'].disconnect(self._detector_connection)
            del self._detector_connection
        except AttributeError:
            pass

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        self._cleanup_signalconnections()
        self._detector_connection = self._instrument.devices['pilatus'].connect('variable-change',
                                                                                self.on_variable_change)

    def _update_indicators(self):
        for vn in self._indicators:
            self.on_variable_change(self._instrument.devices['pilatus'], vn,
                                    self._instrument.devices['pilatus'].get_variable(vn))
        self.on_gain_changed(self._builder.get_object('gain_selector'))

    def on_unmap(self, window):
        self._cleanup_signalconnections()

    def on_variable_change(self, detector, variablename, value):
        if variablename.startswith('temperature'):
            if variablename.endswith('0'):
                if value < 15 or value > 55:
                    state = IndicatorState.ERROR
                elif value < 20 or value > 37:
                    state = IndicatorState.WARNING
                else:
                    state = IndicatorState.OK
            elif variablename.endswith('1'):
                if value < 15 or value > 35:
                    state = IndicatorState.ERROR
                elif value < 20 or value > 33:
                    state = IndicatorState.WARNING
                else:
                    state = IndicatorState.OK
            elif variablename.endswith('2'):
                if value < 15 or value > 45:
                    state = IndicatorState.ERROR
                elif value < 20 or value > 35:
                    state = IndicatorState.WARNING
                else:
                    state = IndicatorState.OK
            else:
                raise NotImplementedError(variablename)
            self._indicators[variablename].set_value('%.2f °C' % value, state)
        elif variablename.startswith('humidity'):
            if variablename.endswith('0') or variablename.endswith('1'):
                if value > 80:
                    state = IndicatorState.ERROR
                elif value > 45:
                    state = IndicatorState.WARNING
                else:
                    state = IndicatorState.OK
            elif variablename.endswith('2'):
                if value > 30:
                    state = IndicatorState.ERROR
                elif value > 10:
                    state = IndicatorState.WARNING
                else:
                    state = IndicatorState.OK
            else:
                raise NotImplementedError(variablename)
            self._indicators[variablename].set_value('%.2f %%' % value, state)
        elif variablename in ['cutoff', 'nimages', 'sel_chip', 'sel_bank', 'sel_module', 'pid', 'controllingPID',
                              'masterPID']:
            self._indicators[variablename].set_value('%d' % value, IndicatorState.NEUTRAL)
        elif variablename == 'tau':
            self._indicators[variablename].set_value('%.1f ns' % (value * 1e9), IndicatorState.NEUTRAL)
        elif variablename in ['trimfile', 'gain', 'targetfile', 'lastcompletedimage', 'lastimage', 'imgpath',
                              'shutterstate', 'imgmode', 'cameradef', 'version', 'cameraSN', 'cameraname', '_status']:
            self._indicators[variablename].set_value(value, IndicatorState.NEUTRAL)
        elif variablename == 'vcmp':
            self._indicators[variablename].set_value('%.3f V' % value, IndicatorState.NEUTRAL)
        elif variablename == 'threshold':
            self._indicators[variablename].set_value('%d eV' % value, IndicatorState.NEUTRAL)
        elif variablename in ['timeleft', 'expperiod', 'exptime']:
            self._indicators[variablename].set_value('%.1f s' % value, IndicatorState.NEUTRAL)
        elif variablename == 'starttime':
            self._indicators[variablename].set_value(str(value), IndicatorState.NEUTRAL)
        elif variablename == 'diskfree':
            value_GB = value / 1024 ** 2
            if value_GB < 10:
                state = IndicatorState.WARNING
            elif value_GB < 2:
                state = IndicatorState.ERROR
            else:
                state = IndicatorState.OK
            self._indicators[variablename].set_value('%.3f GB' % value_GB, state)
        elif variablename in ['wpix', 'hpix']:
            self._indicators['wpix'].set_value('%d×%d' % (self._instrument.devices['pilatus'].get_variable('wpix'),
                                                          self._instrument.devices['pilatus'].get_variable('hpix')),
                                               IndicatorState.NEUTRAL)
        else:
            raise NotImplementedError(variablename)
        if variablename == 'gain':
            for i, gainlabel in enumerate(self._builder.get_object('gain_selector').get_model()):
                if gainlabel[0].startswith(value):
                    self._builder.get_object('gain_selector').set_active(i)
        if variablename == 'threshold':
            self._builder.get_object('threshold_adjustment').set_value(value)

    def on_trim(self, button):
        self._instrument.devices['pilatus'].set_threshold(self._builder.get_object('threshold_adjustment').get_value(),
                                                          self._builder.get_object('gain_selector').get_active_text())

    def on_gain_changed(self, gainselector):
        # set threshold limits from
        if gainselector.get_active_text() == 'lowG':
            self._builder.get_object('threshold_adjustment').set_lower(6685)
            self._builder.get_object('threshold_adjustment').set_upper(20202)
        elif gainselector.get_active_text() == 'midG':
            self._builder.get_object('threshold_adjustment').set_lower(4425)
            self._builder.get_object('threshold_adjustment').set_upper(14328)
        elif gainselector.get_active_text() == 'highG':
            self._builder.get_object('threshold_adjustment').set_lower(3814)
            self._builder.get_object('threshold_adjustment').set_upper(11614)
        low = self._builder.get_object('threshold_adjustment').get_lower()
        up = self._builder.get_object('threshold_adjustment').get_upper()
        value = self._builder.get_object('threshold_adjustment').get_value()
        if value < low:
            self._builder.get_object('threshold_adjustment').set_value(low)
        if value > up:
            self._builder.get_object('threshold_adjustment').set_value(up)
