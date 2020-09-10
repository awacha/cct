from typing import Optional

from .backend import PilatusBackend
from ...device.frontend import DeviceFrontend
import enum


class PilatusGain(enum.Enum):
    Low = 'lowG'
    Mid = 'midG'
    High = 'highG'


class PilatusDetector(DeviceFrontend):
    devicename = 'Pilatus'
    devicetype = 'detector'
    backendclass = PilatusBackend

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def trim(self, energythreshold: float, gain: PilatusGain):
        self.issueCommand('trim', energythreshold, gain.value)

    def expose(self, relative_imgpath, firstfilename, exptime, nimages, delay):
        self.issueCommand('expose', relative_imgpath, firstfilename, exptime, nimages, delay)

    def stopexposure(self):
        self.issueCommand('stopexposure')



