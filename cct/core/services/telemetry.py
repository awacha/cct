import datetime
import os
import time

from gi.repository import GLib

from .service import Service
from ..utils.callback import SignalFlags
from ..utils.telemetry import TelemetryInfo


class TelemetryManager(Service):
    """A class for storing and saving telemetry information and
    occasionally logging memory usage."""

    name = 'telemetrymanager'

    state = {'memlog_file_basename': 'memoryusage',
             'memlog_interval': 30.0,}

    __signals__ = {
        # emitted when telemetry information arrives from a unit. ARguments are
        # the unit name and the telemetry object.
        'telemetry': (SignalFlags.RUN_FIRST, None, (str, object))
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.telemetries = {}
        self.timestamps = {}
        self._memlog_timeout_handle = None
        self.memlog_file = None

    def start(self):
        super().start()
        self.init_memlog_file()
        self._memlog_timeout_handle = GLib.timeout_add(self.state['memlog_interval'] * 1000,
                                                       self.write_memlog_line)

    def incoming_telemetry(self, label, telemetry: TelemetryInfo):
        self.telemetries[label] = telemetry
        self.timestamps[label] = time.monotonic()
        self.emit('telemetry', label, telemetry)

    def get_telemetry(self, label) -> TelemetryInfo:
        if label is None:
            tm = sum(list(self.telemetries.values()))
            tm.processname = '-- overall --'
            return tm
        else:
            return self.telemetries[label]

    def init_memlog_file(self):
        memlogfiles = [f for f in os.listdir(self.instrument.config['path']['directories']['log']) if
                       f.rsplit('.', 1)[0] == self.state['memlog_file_basename']]
        if not memlogfiles:
            self.memlog_file = self.state['memlog_file_basename'] + '.0'
        else:
            maxidx = max([int(f.rsplit('.', 1)[1]) for f in memlogfiles])
            self.memlog_file = self.state['memlog_file_basename'] + '.{:d}'.format(maxidx + 1)
        self.memlog_file = os.path.join(self.instrument.config['path']['directories']['log'], self.memlog_file)
        with open(self.memlog_file, 'xt', encoding='utf-8') as f:
            f.write('# CCT memory log file created {}\n'.format(datetime.datetime.now()))
            f.write('# Epoch (sec)\tUptime (sec)\tMain (MB)')
            for d in sorted(self.instrument.devices):
                f.write('\t {} (MB)'.format(d))
            for s in sorted(self.instrument.services):
                f.write('\t {} (MB)'.format(s))
            f.write('\n')

    def write_memlog_line(self):
        with open(self.memlog_file, 'at', encoding='utf-8') as f:
            try:
                tm = self.telemetries['main']
            except KeyError:
                return True
            memsizes = []
            for d in sorted(self.instrument.devices):
                try:
                    tm = self.telemetries[d]
                    assert isinstance(tm, TelemetryInfo)
                    memsizes.append(tm.memusage)
                except KeyError:
                    memsizes.append(0)
            for d in sorted(self.instrument.services):
                try:
                    tm = self.telemetries[d]
                    assert isinstance(tm, TelemetryInfo)
                    memsizes.append(tm.memusage)
                except KeyError:
                    memsizes.append(0)
            data = [time.time(), time.monotonic() - self.starttime, sum(memsizes)] + memsizes
            f.write('\t'.join(['{:.3f}'.format(d) for d in data]) + '\n')
        return True

    def stop(self):
        GLib.source_remove(self._memlog_timeout_handle)
        super().stop()

    def __getitem__(self, item):
        return self.get_telemetry(item)

    def keys(self):
        return self.telemetries.keys()
