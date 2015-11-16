import logging
import multiprocessing
import resource

from gi.repository import GLib

from ..core.toolwindow import ToolWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_telemetry():
    return {'processname': multiprocessing.current_process().name,
            'self': resource.getrusage(resource.RUSAGE_SELF),
            'children': resource.getrusage(resource.RUSAGE_CHILDREN),
            'inqueuelen': 0}


class DummyTm(object):
    ru_utime = None
    ru_stime = None
    ru_maxrss = None
    ru_minflt = None
    ru_majflt = None
    ru_inblock = None
    ru_oublock = None
    ru_nvcsw = None
    ru_nivcsw = None


class Telemetry(ToolWindow):
    def _cleanup_connections(self):
        try:
            GLib.source_remove(self._idle_handler)
            del self._idle_handler
        except AttributeError:
            pass
        try:
            for dev in list(self._telemetryconnections):
                dev.disconnect(self._telemetryconnections[dev])
                del self._telemetryconnections[dev]
        except AttributeError:
            pass

    def on_unmap(self, window):
        self._cleanup_connections()

    def on_map(self, window):
        self._cleanup_connections()
        self._telemetries = {}
        self._telemetries_outstanding = []
        self._telemetryconnections = {}
        for d in self._instrument.devices:
            self._telemetryconnections[self._instrument.devices[d]] = self._instrument.devices[d].connect('telemetry',
                                                                                                          self.on_telemetry,
                                                                                                          d)
        self._telemetryconnections[self._instrument.exposureanalyzer] = self._instrument.exposureanalyzer.connect(
            'telemetry', self.on_telemetry, 'exposureanalyzer')
        self.on_timeout()
        self._idle_handler = GLib.timeout_add(1000, self.on_timeout)

    def on_process_changed(self, selector):
        model = self._builder.get_object('telemetrymodel')
        process = selector.get_active_text()
        if process is None:
            return
        if process == '-- overall --':
            tm = {}
            for what in ['self', 'children']:
                tm[what] = DummyTm()
                tm[what].ru_utime = sum([self._telemetries[k][what].ru_utime for k in self._telemetries])
                tm[what].ru_stime = sum([self._telemetries[k][what].ru_stime for k in self._telemetries])
                tm[what].ru_maxrss = sum([self._telemetries[k][what].ru_maxrss for k in self._telemetries])
                tm[what].ru_minflt = sum([self._telemetries[k][what].ru_minflt for k in self._telemetries])
                tm[what].ru_majflt = sum([self._telemetries[k][what].ru_majflt for k in self._telemetries])
                tm[what].ru_inblock = sum([self._telemetries[k][what].ru_inblock for k in self._telemetries])
                tm[what].ru_oublock = sum([self._telemetries[k][what].ru_oublock for k in self._telemetries])
                tm[what].ru_nvcsw = sum([self._telemetries[k][what].ru_nvcsw for k in self._telemetries])
                tm[what].ru_nivcsw = sum([self._telemetries[k][what].ru_nivcsw for k in self._telemetries])
        else:
            logger.debug('Process: %s' % process)
            tm = {'self': self._telemetries[process]['self'],
                  'children': self._telemetries[process]['children'],
                  }
        model.clear()
        model.append(['User time (sec):', '%.2f' % tm['self'].ru_utime, '%.2f' % tm['children'].ru_utime,
                      '%.2f' % (tm['self'].ru_utime + tm['children'].ru_utime)])
        model.append(['System time (sec):', '%.2f' % tm['self'].ru_stime, '%.2f' % tm['children'].ru_stime,
                      '%.2f' % (tm['self'].ru_stime + tm['children'].ru_stime)])
        model.append(['Memory usage (MB):', '%.2f' % (tm['self'].ru_maxrss * resource.getpagesize() / 1024 ** 2),
                      '%.2f' % (tm['children'].ru_maxrss * resource.getpagesize() / 1024 ** 2),
                      '%.2f' % (
                      (tm['self'].ru_maxrss + tm['children'].ru_maxrss) * resource.getpagesize() / 1024 ** 2)])
        model.append(['Page faults without I/O:', str(tm['self'].ru_minflt), str(tm['children'].ru_minflt),
                      str(tm['self'].ru_minflt + tm['children'].ru_minflt)])
        model.append(['Page faults with I/O:', str(tm['self'].ru_majflt), str(tm['children'].ru_majflt),
                      str(tm['self'].ru_majflt + tm['children'].ru_majflt)])
        model.append(['Number of fs input operations:', str(tm['self'].ru_inblock), str(tm['children'].ru_inblock),
                      str(tm['self'].ru_inblock + tm['children'].ru_inblock)])
        model.append(['Number of fs output operations:', str(tm['self'].ru_oublock), str(tm['children'].ru_oublock),
                      str(tm['self'].ru_oublock + tm['children'].ru_oublock)])
        model.append(['Number of voluntary context switches:', str(tm['self'].ru_nvcsw), str(tm['children'].ru_nvcsw),
                      str(tm['self'].ru_nvcsw + tm['children'].ru_nvcsw)])
        model.append(
            ['Number of involuntary context switches:', str(tm['self'].ru_nivcsw), str(tm['children'].ru_nivcsw),
             str(tm['self'].ru_nivcsw + tm['children'].ru_nivcsw)])

    def on_telemetry(self, device, telemetry, devicename):
        logger.debug('Telemetry from %s' % (devicename,))
        self._telemetries[devicename] = telemetry
        self._telemetries_outstanding = [x for x in self._telemetries_outstanding if x != devicename]
        logger.debug('Outstanding telemetries: %s' % self._telemetries_outstanding)
        selector = self._builder.get_object('process_selector')
        if devicename not in [x[0] for x in selector.get_model()]:
            prevselected = selector.get_active_text()
            selector.remove_all()
            selector.append_text('-- overall --')
            for i, dn in enumerate(sorted(self._telemetries)):
                selector.append_text(dn)
                if dn == prevselected:
                    selector.set_active(i)
            if selector.get_active_text() is None:
                selector.set_active(0)
        if (devicename == selector.get_active_text()) or (selector.get_active_text() == '-- overall --'):
            self.on_process_changed(selector)

    def on_timeout(self):
        self.on_telemetry(None, get_telemetry(), 'main')
        for d in self._instrument.devices:
            if d not in self._telemetries_outstanding:
                self._telemetries_outstanding.append(d)
                self._instrument.devices[d].get_telemetry()
        d = 'exposureanalyzer'
        if d not in self._telemetries_outstanding:
            self._telemetries_outstanding.append(d)
            self._instrument.exposureanalyzer.get_telemetry()
        return True
