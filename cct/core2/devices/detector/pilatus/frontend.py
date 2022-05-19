import enum
import logging
from typing import Tuple, Any

from .backend import PilatusBackend
from ...device.frontend import DeviceFrontend, DeviceType
from ....sensors.hygrometer import Hygrometer
from ....sensors.thermometer import Thermometer


class PilatusGain(enum.Enum):
    Low = 'lowG'
    Mid = 'midG'
    High = 'highG'


class PilatusDetector(DeviceFrontend):
    devicename = 'PilatusDetector'
    devicetype = DeviceType.Detector
    vendor = 'Dectris Ltd.'
    backendclass = PilatusBackend
    loglevel = logging.INFO

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sensors = [Thermometer(f'Power board temperature', self.name, 0, '°C', paniconerror=True),
                        Thermometer(f'Base plate temperature', self.name, 1, '°C', paniconerror=True),
                        Thermometer(f'Sensor temperature', self.name, 2, '°C', paniconerror=True),
                        Hygrometer(f'Power board humidity', self.name, 3, '%', paniconerror=True),
                        Hygrometer(f'Base plate humidity', self.name, 4, '%', paniconerror=True),
                        Hygrometer(f'Sensor humidity', self.name, 5, '%', paniconerror=True),
                        ]

    def trim(self, energythreshold: float, gain: PilatusGain):
        thresholdmin, thresholdmax = self.thresholdLimits(gain)
        if energythreshold < thresholdmin or energythreshold > thresholdmax:
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

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename == 'temperature':
            for i in range(3):
                self.sensors[i].update(newvalue[i])
        elif variablename == 'humidity':
            for i in range(3):
                self.sensors[3 + i].update(newvalue[i])
        elif variablename == 'temperaturelimits':
            for i in range(3):
                self.sensors[i].setErrorLimits(*newvalue[i])
        elif variablename == 'humiditylimits':
            for i in range(3):
                self.sensors[3 + i].setErrorLimits(*newvalue[i])
