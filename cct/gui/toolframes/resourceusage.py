import time
from typing import Optional, Tuple

from ..core.toolframe import ToolFrame
from ...core.utils.telemetry import TelemetryInfo


def split_time(time_seconds) -> Tuple[int, int, int, int]:
    days = time_seconds // (24 * 3600)
    hours = (time_seconds - days * (24 * 3600)) // 3600
    mins = (time_seconds - days * 24 * 3600 - hours * 3600) // 60
    secs = (time_seconds - days * 24 * 3600 - hours * 3600 - mins * 60)
    return int(days), int(hours), int(mins), int(secs)


class ResourceUsageFrame(ToolFrame):
    def __init__(self, *args, **kwargs):
        self._telemetry_connection = None
        super().__init__(*args, **kwargs)

    def init_gui(self, *args, **kwargs):
        self._telemetry_connection = self.instrument.services['telemetrymanager'].connect('telemetry',
                                                                                          self.on_telemetry)

    def cleanup(self):
        if self._telemetry_connection is not None:
            self.instrument.services['telemetrymanager'].disconnect(self._telemetry_connection)
            self._telemetry_connection = None
        return super().cleanup()

    def on_telemetry(self, telemetrymanager, label: Optional[str], tm: TelemetryInfo):
        if label is not None:
            return False
        self.builder.get_object('uptime_label').set_text('{:d}d.{:d}:{:d}:{:d}'.format(*split_time(
            time.monotonic() - self.instrument.starttime)))
        self.builder.get_object('livetime_label').set_text('{:d}d.{:d}:{:d}:{:d}'.format(*split_time(
            tm.systemtime + tm.usertime)))
        self.builder.get_object('memory_label').set_text(
            '{:.2f} MB'.format(tm.memusage / 1024 / 1024))
        self.builder.get_object('freemem_label').set_text(
            '{:.2f} from {:.2f} GB ({:.2f} %)'.format(tm.freephysmem / 1073741824, tm.totalphysmem / 1073741824,
                                                      tm.freephysmem / tm.totalphysmem * 100))
        self.builder.get_object('freeswap_label').set_text(
            '{:.2f} from {:.2f} GB ({:.2f} %)'.format(tm.freeswap / 1073741824, tm.totalswap / 1073741824,
                                                      tm.freeswap / tm.totalswap * 100))
        self.builder.get_object('loadavg_label').set_text(tm.loadavg)
        return False
