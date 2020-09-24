from typing import Optional, Tuple

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
        thresholdmin, thresholdmax = self.thresholdLimits(gain)
        if energythreshold < thresholdmin or energythreshold>thresholdmax:
            raise ValueError(f'Invalid threshold value ({energythreshold} eV) for this gain setting ({gain.value}).')
        self.issueCommand('trim', energythreshold, gain.value)

    def expose(self, relative_imgpath, firstfilename, exptime, nimages, delay):
        self.issueCommand('expose', relative_imgpath, firstfilename, exptime, nimages, delay)

    def stopexposure(self):
        self.issueCommand('stopexposure')

    @staticmethod
    def thresholdLimits(gain: PilatusGain) -> Tuple[float, float]:
        if gain == PilatusGain.Low:
            return 6685, 20202
        elif gain == PilatusGain.Mid:
            return 4425, 14328
        elif gain == PilatusGain.High:
            return 3814, 11614
        else:
            raise ValueError(f'Invalid gain {gain}')





