import time
from typing import Optional, Tuple

from PyQt5 import QtWidgets

from .resourceconsumption_ui import Ui_DockWidget
from ...core.mixins import ToolWindow
from ....core.instrument.instrument import Instrument
from ....core.services.telemetry import TelemetryManager, TelemetryInfo, ServiceError


def split_time(time_seconds) -> Tuple[int, int, int, int]:
    days = time_seconds // (24 * 3600)
    hours = (time_seconds - days * (24 * 3600)) // 3600
    mins = (time_seconds - days * 24 * 3600 - hours * 3600) // 60
    secs = (time_seconds - days * 24 * 3600 - hours * 3600 - mins * 60)
    return int(days), int(hours), int(mins), int(secs)


class ResourceConsumption(QtWidgets.QDockWidget, Ui_DockWidget, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QDockWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._telemetryconnections=[]
        self.setupUi(self)

    def setupUi(self, DockWidget):
        Ui_DockWidget.setupUi(self, self)
        assert isinstance(self.credo, Instrument)
        tm = self.credo.services['telemetrymanager']
        assert isinstance(tm, TelemetryManager)
        self._telemetryconnections=[tm.connect('telemetry', self.onTelemetry)]
        try:
            self.onTelemetry(tm, None, tm.get_telemetry(None))
        except ServiceError:
            # this can happen if no telemetries have been acquired yet.
            pass

    def onTelemetry(self, telemetrymanager:TelemetryManager, category:Optional[str], telemetrydata:TelemetryInfo):
        if category is not None:
            return False
        self.freeMemLabel.setText('{:.2f} from {:.2f} GB ({:.2f} %)'.format(
            telemetrydata.freephysmem / 1073741824,
            telemetrydata.totalphysmem / 1073741824,
            telemetrydata.freephysmem / telemetrydata.totalphysmem * 100))
        self.freeSwapLabel.setText('{:.2f} from {:.2f} GB ({:.2f} %)'.format(
            telemetrydata.freeswap / 1073741824,
            telemetrydata.totalswap / 1073741824,
            telemetrydata.freeswap / telemetrydata.totalswap * 100))
        self.wallTimeLabel.setText('{:d}d.{:d}:{:d}:{:d}'.format(*split_time(
            time.monotonic() - self.credo.starttime)))
        self.liveTimeLabel.setText('{:d}d.{:d}:{:d}:{:d}'.format(*split_time(
            telemetrydata.systemtime+telemetrydata.usertime)))
        self.memLabel.setText('{:.2f} MB'.format(telemetrydata.memusage/(1048576)))
        self.loadAvgLabel.setText(telemetrydata.loadavg)

    def cleanup(self):
        for c in self._telemetryconnections:
            self.credo.services['telemetrymanager'].disconnect(c)
        self._telemetryconnections=[]
