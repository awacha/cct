import resource
import time

from ..core.toolframe import ToolFrame


def split_time(time_seconds):
    days = time_seconds // (24 * 3600)
    hours = (time_seconds - days * (24 * 3600)) // 3600
    mins = (time_seconds - days * 24 * 3600 - hours * 3600) // 60
    secs = (time_seconds - days * 24 * 3600 - hours * 3600 - mins * 60)
    return days, hours, mins, secs


class ResourceUsageFrame(ToolFrame):
    def _init_gui(self, *args):
        self.on_telemetry(self._instrument, 'main', 'service', self._instrument.get_telemetry())
        self._telemetry_connection=self._instrument.connect('telemetry', self.on_telemetry)

    def on_telemetry(self, instrument, device, devicetype, tm):
        if device is not None:
            return False
        uptime = time.time() - self._application._starttime
        self._builder.get_object('uptime_label').set_text('%dd.%d:%d:%d' % split_time(uptime))
        self._builder.get_object('livetime_label').set_text('%dd.%d:%d:%d' % split_time(
            tm['self'].ru_stime + tm['children'].ru_stime + tm['self'].ru_utime + tm['children'].ru_utime))
        self._builder.get_object('memory_label').set_text(
            '%.2f MB' % ((tm['self'].ru_maxrss + tm['children'].ru_maxrss) * resource.getpagesize() / 1024 ** 2))
        self._builder.get_object('freemem_label').set_text(
            '%.2f from %.2f GB (%.2f %%)'%(tm['freephysmem']/1073741824,tm['totalphysmem']/1073741824,
                                           tm['freephysmem']/tm['totalphysmem']*100))
        self._builder.get_object('freeswap_label').set_text(
            '%.2f from %.2f GB (%.2f %%)' % (tm['freeswap']/1073741824, tm['totalswap']/1073741824,
                                             tm['freeswap'] / tm['totalswap'] * 100))
        self._builder.get_object('loadavg_label').set_text(
            tm['loadavg'])
        return False

    def on_unmap(self, widget):
        try:
            self._instrument.disconnect(self._telemetry_connection)
            del self._telemetry_connection
        except AttributeError:
            pass
