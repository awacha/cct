from ..core.toolwindow import ToolWindow
from ..core.indicator import Indicator, IndicatorState


class TPG201(ToolWindow):
    def _init_gui(self, *args):
        self._indicator = Indicator('Pressure', 'N/A', IndicatorState.UNKNOWN)
        self._builder.get_object('alignment').add(self._indicator)
        self.on_map(self._window)

    def on_map(self, window):
        self._disconnect_vacuumgauge()
        vac = self._instrument.environmentcontrollers['vacuum']
        self._vacconnect = vac.connect('variable-change', self.on_variable_change)
        self.on_variable_change(vac, 'pressure', vac.get_variable('pressure'))

    def _disconnect_vacuumgauge(self):
        try:
            self._instrument.environmentcontrollers['vacuum'].disconnect(self._vacconnect)
            del self._vacconnect
        except AttributeError:
            pass

    def on_unmap(self, window):
        self._disconnect_vacuumgauge()

    def on_variable_change(self, vacgauge, variable, newvalue):
        if variable == 'pressure':
            if newvalue > 1:
                state = IndicatorState.ERROR
            elif newvalue > 0.1:
                state = IndicatorState.WARNING
            else:
                state = IndicatorState.OK
            self._indicator.set_value(str(newvalue) + ' mbar', state)
        return False
