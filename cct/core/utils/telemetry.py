import multiprocessing
import os
import resource
import time

import psutil


class TelemetryInfo(object):
    def __init__(self):
        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        la = ', '.join([str(f) for f in os.getloadavg()])
        self.timestamp = time.monotonic()
        self.processname = multiprocessing.current_process().name,
        self.rusage_self = resource.getrusage(resource.RUSAGE_SELF),
        self.inqueuelen = 0
        self.freephysmem = vm.available
        self.totalphysmem = vm.total
        self.freeswap = sm.free
        self.totalswap = sm.total
        self.loadavg = la

    @property
    def memusage(self):
        assert isinstance(self.rusage_self, resource.struct_rusage)
        return self.rusage_self.ru_maxrss * resource.getpagesize()

    @property
    def usertime(self):
        assert isinstance(self.rusage_self, resource.struct_rusage)
        return self.rusage_self.ru_utime

    @property
    def systemtime(self):
        assert isinstance(self.rusage_self, resource.struct_rusage)
        return self.rusage_self.ru_stime

    @property
    def pagefaultswithoutio(self):
        assert isinstance(self.rusage_self, resource.struct_rusage)
        return self.rusage_self.ru_minflt

    @property
    def pagefaultswithio(self):
        assert isinstance(self.rusage_self, resource.struct_rusage)
        return self.rusage_self.ru_majflt

    @property
    def fsinput(self):
        assert isinstance(self.rusage_self, resource.struct_rusage)
        return self.rusage_self.ru_inblock

    @property
    def fsoutput(self):
        assert isinstance(self.rusage_self, resource.struct_rusage)
        return self.rusage_self.ru_oublock

    @property
    def voluntarycontextswitches(self):
        assert isinstance(self.rusage_self, resource.struct_rusage)
        return self.rusage_self.ru_nvcsw

    @property
    def involuntarycontextswitches(self):
        assert isinstance(self.rusage_self, resource.struct_rusage)
        return self.rusage_self.ru_nivcsw

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
            if a in ['timestamp', 'freephysmem', 'totalphysmem', 'freeswap', 'totalswap']:
                setattr(tm, a, getattr(self, a) + getattr(other, a))
        return tm

    def user_attributes(self):
        return [d for d in self.__dict__ if d not in self.__class__.__dict__]
