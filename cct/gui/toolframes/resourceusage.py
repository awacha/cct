import resource
import time

from gi.repository import GLib

from ..core.toolframe import ToolFrame


def split_time(time_seconds):
    days = time_seconds // (24 * 3600)
    hours = (time_seconds - days * (24 * 3600)) // 3600
    mins = (time_seconds - days * 24 * 3600 - hours * 3600) // 60
    secs = (time_seconds - days * 24 * 3600 - hours * 3600 - mins * 60)
    return days, hours, mins, secs


class ResourceUsage(ToolFrame):
    def _init_gui(self, *args):
        self.on_timeout()
        self._idle_handler = GLib.timeout_add(1000, self.on_timeout)

    def on_timeout(self):
        tm = self._instrument.get_telemetry(None)
        uptime = time.time() - self._application._starttime
        self._builder.get_object('uptime_label').set_text('%dd.%d:%d:%d' % split_time(uptime))
        self._builder.get_object('usertime_label').set_text(
            '%dd.%d:%d:%d' % split_time(tm['self'].ru_utime + tm['children'].ru_utime))
        self._builder.get_object('systemtime_label').set_text(
            '%dd.%d:%d:%d' % split_time(tm['self'].ru_stime + tm['children'].ru_stime))
        self._builder.get_object('livetime_label').set_text('%dd.%d:%d:%d' % split_time(
            tm['self'].ru_stime + tm['children'].ru_stime + tm['self'].ru_utime + tm['children'].ru_utime))
        try:
            self._builder.get_object('usersystemratio_label').set_text('%.2f %%' % (
            (tm['self'].ru_utime + tm['children'].ru_utime) / (tm['self'].ru_stime + tm['children'].ru_stime) * 100))
        except ZeroDivisionError:
            self._builder.get_object('usersystemratio_label').set_text('--')
        self._builder.get_object('memory_label').set_text(
            '%.2f MB' % ((tm['self'].ru_maxrss + tm['children'].ru_maxrss) * resource.getpagesize() / 1024 ** 2))
        return True

    def on_unmap(self, widget):
        try:
            GLib.source_remove(self._idle_handler)
            del self._idle_handler
        except AttributeError:
            pass
