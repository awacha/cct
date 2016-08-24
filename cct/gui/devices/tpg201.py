from ..core.indicator import Indicator, IndicatorState
from ..core.toolwindow import ToolWindow


class TPG201(ToolWindow):
    required_devices = ['tpg201']

    def __init__(self, *args, **kwargs):
        self.indicator = None
        super().__init__(*args, **kwargs)

    def init_gui(self, *args):
        self.indicator = Indicator('Pressure', 'N/A', IndicatorState.UNKNOWN)
        self.builder.get_object('alignment').add(self.indicator)
        self.update_indicators()

    def update_indicators(self):
        vac = self.instrument.get_device('vacuum')
        self.on_device_variable_change(vac, 'pressure', vac.get_variable('pressure'))

    def on_device_variable_change(self, vacgauge, variable, newvalue):
        if variable == 'pressure':
            if newvalue > 1:
                state = IndicatorState.ERROR
            elif newvalue > 0.1:
                state = IndicatorState.WARNING
            else:
                state = IndicatorState.OK
            self.indicator.set_value('%.3f mbar' % newvalue, state)
        return False
