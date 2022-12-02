import enum
import logging
from typing import Tuple, Any

import h5py

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

    def exposeprepared(self, firstfilename):
        self.issueCommand('expose', firstfilename)

    def prepareexposure(self, relative_imgpath: str, exptime: float, nimages: int, delay: float):
        self.issueCommand('prepareexposure', relative_imgpath, exptime, nimages, delay)

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

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        # variables to be set later:
        #   - data
        #   - data_errors
        #   - distance
        #   - polar_angle
        #   - azimuthal_angle
        #   - x_pixel_size and y_pixel_size (camserver does not report it, it is set outside, in the geometry)
        #   - beam_center_x
        #   - beam_center_y
        #   - pixel_mask
        grp = super().toNeXus(grp)
        grp.attrs['NX_class'] = 'NXdetector'
        grp.attrs['default'] = 'data'
        self.create_hdf5_dataset(grp, 'detector_number', 1)
        self.create_hdf5_dataset(grp, 'description', 'Pilatus-300k, Dectris Ltd.')
        self.create_hdf5_dataset(grp, 'serial_number', self.get('cameraSN'))
        self.create_hdf5_dataset(grp, 'local_name', self.get('cameraname'))
        self.create_hdf5_dataset(grp, 'dead_time', 0.0, units='ms')
        self.create_hdf5_dataset(grp, 'type', 'CMOS')
        self.create_hdf5_dataset(grp, 'layout', 'area')
        self.create_hdf5_dataset(grp, 'count_time', self.get('exptime'), units='s')
        self.create_hdf5_dataset(grp, 'angular_calibration_applied', False)
        self.create_hdf5_dataset(grp, 'flatfield_applied', True)
        self.create_hdf5_dataset(grp, 'countrate_correction_applied', self.get('tau') > 0)
        self.create_hdf5_dataset(grp, 'bit_depth_readout', 10)
        self.create_hdf5_dataset(grp, 'detector_readout_time', 0.0023, units='s')
        self.create_hdf5_dataset(grp, 'frame_time', self.get('expperiod'), units='s')
        self.create_hdf5_dataset(grp, 'gain_setting', self.get('gain'))
        self.create_hdf5_dataset(grp, 'saturation_value', self.get('cutoff'))
        self.create_hdf5_dataset(grp, 'sensor_material', 'Si')
        self.create_hdf5_dataset(grp, 'sensor_thickness', '0.450', units='mm')
        self.create_hdf5_dataset(grp, 'threshold_energy', self.get('threshold'), units='eV')
        return grp
