import logging
import resource

from gi.repository import GLib

from ..core.toolwindow import ToolWindow

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Telemetry(ToolWindow):
    def on_unmap(self, window):
        try:
            GLib.source_remove(self._idle_handler)
            del self._idle_handler
        except AttributeError:
            pass

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        self.on_timeout()
        try:
            GLib.source_remove(self._idle_handler)
            del self._idle_handler
        except AttributeError:
            pass
        self._idle_handler = GLib.timeout_add(1000, self.on_timeout)

    def on_process_changed(self, selector):
        self.update_telemetry()

    def update_selector(self):
        selector = self._builder.get_object('process_selector')
        prevselected = selector.get_active_text()
        selector.remove_all()
        for i, k in enumerate(sorted(list(self._instrument.get_telemetrykeys()) + ['-- overall --'])):
            selector.append_text(k)
            if k == prevselected:
                selector.set_active(i)
        if selector.get_active_text() is None:
            selector.set_active(0)

    def update_telemetry(self):
        selector = self._builder.get_object('process_selector')
        model = self._builder.get_object('telemetrymodel')
        process = selector.get_active_text()
        if process is None:
            return
        if process == '-- overall --':
            tm = self._instrument.get_telemetry(None)
        else:
            logger.debug('Process: %s' % process)
            tm = self._instrument.get_telemetry(process)
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


    def on_timeout(self):
        newkeys = list(self._instrument.get_telemetrykeys())
        if not (hasattr(self, '_telemetrykeys')):
            self._telemetrykeys = []
        if self._telemetrykeys != newkeys:
            self._telemetrykeys = newkeys
            self.update_selector()
        self.update_telemetry()
        return True
