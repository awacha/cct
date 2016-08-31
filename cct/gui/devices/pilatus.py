import logging

from ..core.indicator import Indicator, IndicatorState
from ..core.toolwindow import ToolWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Pilatus(ToolWindow):
    required_devices = ['pilatus']

    def __init__(self, *args, **kwargs):
        self.indicators = {}
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        grid = self.builder.get_object('constants_grid')
        for row, column, vn, label in [(0, 0, '_status', 'Camera state'),
                                       (0, 1, 'cameraname', 'Camera name'),
                                       (0, 2, 'cameraSN', 'Serial number'),
                                       (0, 3, 'version', 'Camserver version'),
                                       (0, 4, 'cameradef', 'Camera definition'),
                                       (0, 5, 'wpix', 'Image size')]:
            self.indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            grid.attach(self.indicators[vn], column, row, 1, 1)
        grid = self.builder.get_object('lowlevel_grid')
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
            self.indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            grid.attach(self.indicators[vn], column, row, 1, 1)
        grid = self.builder.get_object('highlevel_grid')
        for row, column, vn, label in [(0, 0, 'exptime', 'Exposure time'),
                                       (0, 1, 'expperiod', 'Exposure period'),
                                       (0, 2, 'nimages', 'Number of images'),
                                       # (0, 3, 'starttime', 'Start time'),
                                       (0, 4, 'timeleft', 'Time left'),
                                       (0, 5, 'targetfile', 'Target file'),
                                       (1, 0, 'threshold', 'Threshold'),
                                       (1, 1, 'gain', 'Gain'),
                                       (1, 2, 'vcmp', 'Vcmp'),
                                       (1, 3, 'trimfile', 'Trim file'),
                                       (1, 4, 'tau', 'Tau'),
                                       (1, 5, 'cutoff', 'Cutoff'), ]:
            self.indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            grid.attach(self.indicators[vn], column, row, 1, 1)
        grid = self.builder.get_object('ambient_grid')
        for row, column, vn, label in [(0, 0, 'temperature0', 'Power board temp.'),
                                       (0, 1, 'temperature1', 'Base plate temp.'),
                                       (0, 2, 'temperature2', 'Sensor temp.'),
                                       (0, 3, 'humidity0', 'Power board humidity'),
                                       (0, 4, 'humidity1', 'Base plate humidity'),
                                       (0, 5, 'humidity2', 'Sensor humidity')]:
            self.indicators[vn] = Indicator(label, '--', IndicatorState.UNKNOWN)
            grid.attach(self.indicators[vn], column, row, 1, 1)
        self.update_indicators()

    def update_indicators(self):
        for vn in self.indicators:
            self.on_device_variable_change(self.instrument.get_device('pilatus'), vn,
                                           self.instrument.get_device('pilatus').get_variable(vn))
        self.on_gain_changed(self.builder.get_object('gain_selector'))

    def on_device_variable_change(self, detector, variablename, value):
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
                state = IndicatorState.UNKNOWN

            self.indicators[variablename].set_value('%.2f °C' % value, state)
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
                state = IndicatorState.UNKNOWN
            self.indicators[variablename].set_value('%.2f %%' % value, state)
        elif variablename in ['cutoff', 'nimages', 'sel_chip', 'sel_bank', 'sel_module', 'pid', 'controllingPID',
                              'masterPID']:
            self.indicators[variablename].set_value('%d' % value, IndicatorState.NEUTRAL)
        elif variablename == 'tau':
            self.indicators[variablename].set_value('%.1f ns' % (value * 1e9), IndicatorState.NEUTRAL)
        elif variablename in ['trimfile', 'gain', 'targetfile', 'lastcompletedimage', 'lastimage', 'imgpath',
                              'shutterstate', 'imgmode', 'cameradef', 'version', 'cameraSN', 'cameraname', '_status']:
            self.indicators[variablename].set_value(value, IndicatorState.NEUTRAL)
        elif variablename == 'vcmp':
            self.indicators[variablename].set_value('%.3f V' % value, IndicatorState.NEUTRAL)
        elif variablename == 'threshold':
            self.indicators[variablename].set_value('%d eV' % value, IndicatorState.NEUTRAL)
        elif variablename in ['timeleft', 'expperiod', 'exptime']:
            self.indicators[variablename].set_value('%.1f s' % value, IndicatorState.NEUTRAL)
        #        elif variablename == 'starttime':
        #            self.indicators[variablename].set_value(str(value), IndicatorState.NEUTRAL)
        elif variablename == 'diskfree':
            value_gigabyte = value / 1024 ** 2
            if value_gigabyte < 10:
                state = IndicatorState.WARNING
            elif value_gigabyte < 2:
                state = IndicatorState.ERROR
            else:
                state = IndicatorState.OK
            self.indicators[variablename].set_value('%.3f GB' % value_gigabyte, state)
        elif variablename in ['wpix', 'hpix']:
            self.indicators['wpix'].set_value('%d×%d' % (self.instrument.get_device('pilatus').get_variable('wpix'),
                                                         self.instrument.get_device('pilatus').get_variable('hpix')),
                                              IndicatorState.NEUTRAL)
        else:
            pass
        if variablename == 'gain':
            for i, gainlabel in enumerate(self.builder.get_object('gain_selector').get_model()):
                if gainlabel[0].startswith(value):
                    self.builder.get_object('gain_selector').set_active(i)
        if variablename == 'threshold':
            self.builder.get_object('threshold_adjustment').set_value(value)

    def on_trim(self, button):
        threshold = self.builder.get_object('threshold_adjustment').get_value()
        gain = self.builder.get_object('gain_selector').get_active_text()
        logger.info('Setting threshold to %f eV (gain %s).' % (threshold, gain))
        self.instrument.get_device('pilatus').set_threshold(threshold, gain)

    def on_gain_changed(self, gainselector):
        # set threshold limits from
        if gainselector.get_active_text() == 'lowG':
            self.builder.get_object('threshold_adjustment').set_lower(6685)
            self.builder.get_object('threshold_adjustment').set_upper(20202)
        elif gainselector.get_active_text() == 'midG':
            self.builder.get_object('threshold_adjustment').set_lower(4425)
            self.builder.get_object('threshold_adjustment').set_upper(14328)
        elif gainselector.get_active_text() == 'highG':
            self.builder.get_object('threshold_adjustment').set_lower(3814)
            self.builder.get_object('threshold_adjustment').set_upper(11614)
        low = self.builder.get_object('threshold_adjustment').get_lower()
        up = self.builder.get_object('threshold_adjustment').get_upper()
        value = self.builder.get_object('threshold_adjustment').get_value()
        if value < low:
            self.builder.get_object('threshold_adjustment').set_value(low)
        if value > up:
            self.builder.get_object('threshold_adjustment').set_value(up)
