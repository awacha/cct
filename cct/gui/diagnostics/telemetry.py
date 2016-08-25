import logging

from ..core.functions import update_comboboxtext_choices
from ..core.toolwindow import ToolWindow
from ...core.services.telemetry import TelemetryManager
from ...core.utils.telemetry import TelemetryInfo

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ResourceUsage(ToolWindow):
    def __init__(self, *args, **kwargs):
        self._telemetry_handler = None
        self._telemetrykeys = []
        super().__init__(*args, **kwargs)

    def on_mainwidget_map(self, window):
        if ToolWindow.on_mainwidget_map(self, window):
            return True
        self._telemetry_handler = self.instrument.services['telemetrymanager'].connect('telemetry', self.on_telemetry)

    def on_process_changed(self, selector):
        process = selector.get_active_text()
        if process == '-- overall --':
            process = None
        self.update_telemetry(process, self.instrument.services['telemetrymanager'][process])

    def update_selector(self):
        return update_comboboxtext_choices(
            self.builder.get_object('process_selector'),
            sorted(list(self.instrument.services['telemetrymanager'].keys()) + ['-- overall --'])
        )

    def update_telemetry(self, label, tm):
        selector = self.builder.get_object('process_selector')
        model = self.builder.get_object('telemetrymodel')
        process = selector.get_active_text()
        if process == '-- overall --':
            tm = self.instrument.services['telemetrymanager'][None]
        elif label != process:
            return
        assert isinstance(tm, TelemetryInfo)
        model.clear()
        model.append(['User time (sec):', '{:.2f}'.format(tm.usertime)])
        model.append(['System time (sec):', '{:.2f}'.format(tm.systemtime)])
        model.append(['Memory usage (MB):', '{:.2f}'.format(tm.memusage / 1024 / 1024)])
        model.append(['Page faults without I/O:', '{:d}'.format(tm.pagefaultswithoutio)])
        model.append(['Page faults with I/O:', '{:d}'.format(tm.pagefaultswithio)])
        model.append(['Number of fs input operations:', '{:d}'.format(tm.fsinput)])
        model.append(['Number of fs output operations:', '{:d}'.format(tm.fsoutput)])
        model.append(['Number of voluntary context switches:', '{:d}'.format(tm.voluntarycontextswitches)])
        model.append(['Number of involuntary context switches:', '{:d}'.format(tm.involuntarycontextswitches)])

        model = self.builder.get_object('telemetry_store')
        model.clear()
        for q in sorted([q_ for q_ in tm.user_attributes()]):
            model.append([q, str(getattr(tm, q))])

    def on_telemetry(self, telemetryservice: TelemetryManager, label: str, telemetry):
        newkeys = list(telemetryservice.keys())
        if self._telemetrykeys != newkeys:
            self._telemetrykeys = newkeys
            self.update_selector()
        self.update_telemetry(label, telemetry)
        return False
