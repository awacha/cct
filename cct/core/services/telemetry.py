import datetime
import os
import resource
import time

from gi.repository import GLib

from .service import Service


class TelemetryManager(Service):
    """A class for storing and saving telemetry information and
    occasionally logging memory usage."""

    name = 'telemetrymanager'

    state = {'memlog_file_basename': 'memoryusage',
             'memlog_interval': 30.0,}

    def __init__(self, instrument, statedict):
        super().__init__(instrument, statedict=statedict)
        self.telemetries = {}
        self.timestamps = {}

    def start(self):
        super().start()
        self.init_memlog_file()
        self._memlog_timeout_handle = GLib.timeout_add(self.state['memlog_interval'] * 1000,
                                                       self.write_memlog_line())

    def incoming_telemetry(self, label, telemetry):
        self.telemetries[label] = telemetry
        self.timestamps[label] = time.monotonic()

    def get_telemetry(self, label):
        return self.telemetries[label]

    def init_memlog_file(self):
        memlogfiles = [f for f in os.listdir(self.instrument.config['path']['directories']['log']) if
                       f.rsplit('.', 1)[0] == self.state['memlog_file_basename']]
        if not memlogfiles:
            self.memlog_file = self.state['memlog_file_basename'] + '.0'
        else:
            maxidx = max([int(f.rsplit('.', 1)[1]) for f in memlogfiles])
            self.memlog_file = self.state['memlog_file_basename'] + '.{:d}'.format(maxidx + 1)
        self.memlog_file = os.path.join(self.config['path']['directories']['log'], self.memlog_file)
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
            s = '{:.3f}\t{:.3f}\t{:.3f}'.format(time.time(),
                                                (datetime.datetime.now() - self._starttime).total_seconds(),
                                                (tm['self'].ru_maxrss + tm[
                                                    'children'].ru_maxrss) * resource.getpagesize() / 1024 ** 2)
            for d in sorted(self.instrument.devices):
                try:
                    tm = self.telemetries[d]
                    s = '{}\t{:.3f}'.format(s, (
                        tm['self'].ru_maxrss + tm['children'].ru_maxrss) * resource.getpagesize() / 1024 ** 2)
                except KeyError:
                    s = '{}\tNaN'.format(s)
            for d in sorted(self.instrument.services):
                try:
                    tm = self.telemetries[d]
                    s = '{}\t{:.3f}'.format(s, (
                        tm['self'].ru_maxrss + tm['children'].ru_maxrss) * resource.getpagesize() / 1024 ** 2)
                except KeyError:
                    s = '{}\tNaN'.format(s)
            f.write(s + '\n')
        return True

    def stop(self):
        GLib.source_remove(self._memlog_timeout_handle)
        super().stop()

    def __getitem__(self, item):
        return self.telemetries[item]
