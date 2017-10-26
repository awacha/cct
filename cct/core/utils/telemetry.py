import multiprocessing
import os
import warnings

try:
    import resource
except ModuleNotFoundError:
    warnings.warn('Module \'resource\' not found. Probably on Windows. CCT won\'t work as expected.')
import time

import psutil


class TelemetryInfo(object):
    """A telemetry information object"""

    def __init__(self):
        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        la = ', '.join([str(f) for f in os.getloadavg()])
        self.timestamp = time.monotonic()
        self.processname = multiprocessing.current_process().name
        self.rusage = resource.getrusage(resource.RUSAGE_SELF)
        self.inqueuelen = 0
        self.freephysmem = vm.available
        self.totalphysmem = vm.total
        self.freeswap = sm.free
        self.totalswap = sm.total
        self.loadavg = la

    @property
    def memusage(self):
        """Return the memory usage in bytes."""
        assert isinstance(self.rusage, resource.struct_rusage)
        return self.rusage.ru_maxrss * resource.getpagesize()

    @property
    def usertime(self):
        assert isinstance(self.rusage, resource.struct_rusage)
        return self.rusage.ru_utime

    @property
    def systemtime(self):
        assert isinstance(self.rusage, resource.struct_rusage)
        return self.rusage.ru_stime

    @property
    def pagefaultswithoutio(self):
        assert isinstance(self.rusage, resource.struct_rusage)
        return self.rusage.ru_minflt

    @property
    def pagefaultswithio(self):
        assert isinstance(self.rusage, resource.struct_rusage)
        return self.rusage.ru_majflt

    @property
    def fsinput(self):
        assert isinstance(self.rusage, resource.struct_rusage)
        return self.rusage.ru_inblock

    @property
    def fsoutput(self):
        assert isinstance(self.rusage, resource.struct_rusage)
        return self.rusage.ru_oublock

    @property
    def voluntarycontextswitches(self):
        assert isinstance(self.rusage, resource.struct_rusage)
        return self.rusage.ru_nvcsw

    @property
    def involuntarycontextswitches(self):
        assert isinstance(self.rusage, resource.struct_rusage)
        return self.rusage.ru_nivcsw

    def attributes(self, type_=None):
        if type_ is None:
            type_ = (str, int, float)
        try:
            type_ = tuple(type_)
        except TypeError:
            type_ = (type_,)
        return [d for d in self.__dict__ if isinstance(getattr(self, d), type_)]

    def __add__(self, other):
        tm = TelemetryInfo()
        for a in set(self.attributes((int, float))).intersection(set(other.attributes((int, float)))):
            if a not in ['timestamp', 'freephysmem', 'totalphysmem', 'freeswap', 'totalswap']:
                setattr(tm, a, getattr(self, a) + getattr(other, a))
        tm.rusage = resource.struct_rusage([a + b for a, b in zip(self.rusage, other.rusage)])
        return tm

    def __radd__(self, other):
        if other == 0:
            # implement this special case, because the built-in sum([tm1, tm2, tm3]) starts with res=0; res = res + tm1
            return self
        else:
            return NotImplemented

    def user_attributes(self):
        return [d for d in self.__dict__ if
                d not in ['timestamp', 'processname', 'freephysmem', 'totalphysmem', 'freeswap', 'totalswap',
                          'rusage', 'inqueuelen', 'loadavg'] + list(self.__class__.__dict__.keys())]
