import logging
from typing import Tuple, Sequence, Dict, Any, Optional, Union

import numpy as np
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtProperty

from ....config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GeometryPreset(QtCore.QObject):
    config: Config
    _state: Dict[str, Any]
    changed = QtCore.pyqtSignal(str, object)

    def _getproperty(self, propertyname: str) -> Any:
        return self._state[propertyname]

    def _setproperty(self, propertyname: str, newvalue: Any):
        try:
            oldvalue = self._state[propertyname]
            if oldvalue == newvalue:
                return
        except KeyError:
            pass
        self._state[propertyname] = newvalue
        self.changed.emit(propertyname, newvalue)

    def _getproperty_config(self, propertyname: str, defaultvalue: Any) -> Any:
        return self.config['geometry'].setdefault(propertyname, defaultvalue)

    def _get_sd(self) -> Tuple[float, float]:
        if (('dist_sample_det' not in self._state)
                or (self._state['dist_sample_det'] is None)
                or (self._state['dist_sample_det'][0] <= 0)):
            value = self.ph3toflightpipes + sum(
                self.flightpipes) + self.lastflightpipetodetector - self.ph3tosample, 0.0
        else:
            value = self._state['dist_sample_det']
            assert isinstance(value, tuple) and (len(value) == 2) and all([isinstance(v, float) for v in value])
        return value

    def _set_sd(self, value: Tuple[float, float]):
        self._state['dist_sample_det'] = (value[0], value[1])
        self.changed.emit('dist_sample_det', value)

    description = pyqtProperty(
        str, lambda self: self._getproperty('description'), lambda self, value: self._setproperty('description', value))
    l1_elements = pyqtProperty(
        list, lambda self: self._getproperty('l1_elements'),
        lambda self, value: self._setproperty('l1_elements', value))
    l2_elements = pyqtProperty(
        list, lambda self: self._getproperty('l2_elements'),
        lambda self, value: self._setproperty('l2_elements', value))
    dist_sample_det = pyqtProperty(
        tuple, _get_sd, _set_sd)
    beamposx = pyqtProperty(
        tuple, lambda self: self._getproperty('beamposx'), lambda self, value: self._setproperty('beamposx', value))
    beamposy = pyqtProperty(
        tuple, lambda self: self._getproperty('beamposy'), lambda self, value: self._setproperty('beamposy', value))
    pinhole1 = pyqtProperty(
        float, lambda self: self._getproperty('pinhole1'), lambda self, value: self._setproperty('pinhole1', value))
    pinhole2 = pyqtProperty(
        float, lambda self: self._getproperty('pinhole2'), lambda self, value: self._setproperty('pinhole2', value))
    pinhole3 = pyqtProperty(
        float, lambda self: self._getproperty('pinhole3'), lambda self, value: self._setproperty('pinhole3', value))
    beamstop = pyqtProperty(
        float, lambda self: self._getproperty('beamstop'), lambda self, value: self._setproperty('beamstop', value))
    mask = pyqtProperty(
        str, lambda self: self._getproperty('mask'), lambda self, value: self._setproperty('mask', value))
    flightpipes = pyqtProperty(
        list, lambda self: self._getproperty('flightpipes'), lambda self, value: self._setproperty('flightpipes', value)
    )

    l1base = pyqtProperty(float, lambda self: self._getproperty_config('l1base', 0.0))
    l2base = pyqtProperty(float, lambda self: self._getproperty_config('l2base', 0.0))
    sourcetoph1 = pyqtProperty(float, lambda self: self._getproperty_config('sourcetoph1', 0.0))
    ph3tosample = pyqtProperty(float, lambda self: self._getproperty_config('ph3tosample', 0.0))
    beamstoptodetector = pyqtProperty(float, lambda self: self._getproperty_config('beamstoptodetector', 0.0))
    isoKFspacer = pyqtProperty(float, lambda self: self._getproperty_config('isoKFspacer', 4.0))
    sourcedivergence = pyqtProperty(float, lambda self: self._getproperty_config('sourcedivergence', 0.0))
    ph3toflightpipes = pyqtProperty(float, lambda self: self._getproperty_config('ph3toflightpipes', 0.0))
    lastflightpipetodetector = pyqtProperty(float,
                                            lambda self: self._getproperty_config('lastflightpipetodetector', 0.0))
    wavelength = pyqtProperty(tuple, lambda self: (self.config['geometry'].setdefault('wavelength', 1.0),
                                                   self.config['geometry'].setdefault('wavelength.err', 0.0)))
    pixelsize = pyqtProperty(tuple, lambda self: (self.config['geometry'].setdefault('pixelsize', 1.0),
                                                  self.config['geometry'].setdefault('pixelsize.err', 0.0002)))

    def __init__(self,
                 config: Config,
                 l1_elements: Optional[Sequence[float]] = None,
                 l2_elements: Optional[Sequence[float]] = None,
                 pinhole1: float = 0.0, pinhole2: float = 0.0, pinhole3: float = 0.0,
                 flightpipes: Optional[Sequence[float]] = None,
                 beamstop: float = 0.0,
                 dist_sample_det: Optional[Tuple[float, float]] = None,
                 beamposx: Tuple[float, float] = (0.0, 0.0),
                 beamposy: Tuple[float, float] = (0.0, 0.0),
                 mask: Optional[str] = None,
                 description: str = ''):
        super().__init__()
        self._state = {}
        self.config = config
        self.l1_elements = list(l1_elements) if l1_elements is not None else []
        self.l2_elements = list(l2_elements) if l2_elements is not None else []
        self.pinhole1 = pinhole1
        self.pinhole2 = pinhole2
        self.pinhole3 = pinhole3
        self.beamstop = beamstop
        self.flightpipes = flightpipes if flightpipes is not None else []
        self.dist_sample_det = dist_sample_det if dist_sample_det is not None else (0.0, 0.0)
        self.beamposx = beamposx
        self.beamposy = beamposy
        self.mask = '' if mask is None else mask
        self.description = description

    def dbeam(self, position: float, withparasitic: bool = True) -> float:
        """Beam diameter in mm-s at position

        Positions are calculated from the 1st pinhole.
        """
        if self.l1 == 0 or self.l2 == 0:
            return np.nan
        elif position < 0:
            # before pinhole #1
            return np.inf
        elif (position > self.l1 + self.l2 + self.ph3tosample + self.dist_sample_det[0] - self.beamstoptodetector) and (
                not withparasitic):
            # direct beam after the beamstop
            return 0
        elif position < self.l1:
            # before pinhole #2
            return self.pinhole1 * 1e-3 + 2 * position / np.cos(self.sourcedivergence)
        elif (position < self.l1 + self.l2) or (not withparasitic):
            # before pinhole #3 or direct beam before the beamstop and after ph #2
            return (position * (self.pinhole2 + self.pinhole1) / self.l1 - self.pinhole1) * 1e-3
        elif position <= self.l1 + self.l2 + self.ph3tosample + self.dist_sample_det[0] - self.beamstoptodetector:
            assert withparasitic  # the direct beam has been handled above.
            # parasitic scattering from PH#1 and PH#2 after PH#3 and before the beamstop face
            return ((position - self.l1) * (self.pinhole2 + self.pinhole3) / self.l2 - self.pinhole2) * 1e-3
        elif position <= self.l1 + self.l2 + self.ph3tosample + self.dist_sample_det[0]:
            assert withparasitic
            # parasitic scattering after the beamstop
            d = ((position - self.l1) * (self.pinhole2 + self.pinhole3) / self.l2 - self.pinhole2) * 1e-3
            return d if d >= self.beamstop else 0
        else:
            assert False

    @property
    def l1(self) -> float:
        return sum(self.l1_elements) + self.l1base + len(self.l1_elements) * self.isoKFspacer

    @property
    def l2(self) -> float:
        return sum(self.l2_elements) + self.l2base + len(self.l2_elements) * self.isoKFspacer

    @property
    def intensity(self) -> float:
        try:
            return self.pinhole1 ** 2 * self.pinhole2 ** 2 / self.l1 ** 2
        except ZeroDivisionError:
            return np.nan

    @property
    def dsample(self) -> float:
        return self.dbeam(self.l1 + self.l2 + self.ph3tosample, withparasitic=False)

    @property
    def dbeamstop(self) -> float:
        return self.dbeam(self.l1 + self.l2 + self.ph3tosample + self.dist_sample_det[0] - self.beamstoptodetector,
                          withparasitic=True)

    @property
    def dpinhole3(self) -> float:
        return self.dbeam(self.l1 + self.l2, False)

    @property
    def is_pinhole3_large_enough(self) -> bool:
        return self.dpinhole3 <= self.pinhole3

    @property
    def is_beamstop_large_enough_direct(self) -> bool:
        return self.dbeam(self.l1 + self.l2 + self.ph3tosample + self.dist_sample_det[0] - self.beamstoptodetector,
                          withparasitic=False) <= self.beamstop

    @property
    def is_beamstop_large_enough_parasitic(self) -> bool:
        return self.dbeamstop <= self.beamstop

    @property
    def rmindetector(self) -> float:
        """Smallest radius of the detector with meaningful scattering"""
        # check if we have a halo from parasitic scattering
        parasitic_ring_diameter = self.dbeam(self.l1 + self.l2 + self.ph3tosample + self.dist_sample_det[0],
                                             withparasitic=True) if not self.is_beamstop_large_enough_parasitic else 0
        direct_ring_diameter = self.dbeam(self.l1 + self.l2 + self.ph3tosample + self.dist_sample_det[0],
                                          withparasitic=False) if not self.is_beamstop_large_enough_direct else 0
        try:
            beamstop_shadow_diameter = (self.beamstop + self.dsample) * self.dist_sample_det[0] / (
                    self.dist_sample_det[0] - self.beamstoptodetector) - self.dsample
        except ZeroDivisionError:
            beamstop_shadow_diameter = np.nan
        return max(parasitic_ring_diameter, direct_ring_diameter, beamstop_shadow_diameter) * 0.5

    def toDict(self) -> Dict[str, Any]:
        return self._state

    @classmethod
    def fromDict(cls, config: Config, dic: Union[Dict[str, Any], Config]) -> "GeometryPreset":
        obj = cls(config)
        if isinstance(dic, Config):
            dic = dic.asdict()
        obj.__setstate__(dic)
        return obj

    def __setstate__(self, state: Dict[str, Any]):
        assert isinstance(state, dict)
        self._state = state.copy()
        if 'dist_sample_det' not in self._state:
            self._state['dist_sample_det'] = None
        if (('dist_sample_det' in self._state) and ('dist_sample_det.err' in self._state) and
                isinstance(self._state['dist_sample_det'], float) and
                isinstance(self._state['dist_sample_det.err'], float)
        ):
            self._state['dist_sample_det'] = (self._state['dist_sample_det'], self._state['dist_sample_det.err'])
            del self._state['dist_sample_det.err']
        try:
            del self._state['dist_sample_det.err']
        except KeyError:
            pass

    def __getstate__(self):
        return self._state

    @property
    def qmin(self) -> float:
        try:
            return 4 * np.pi * np.sin(0.5 * np.arctan(self.rmindetector / self.dist_sample_det[0])) / self.wavelength[0]
        except ZeroDivisionError:
            return np.nan

    @property
    def Rgmax(self) -> float:
        try:
            return 1 / self.qmin
        except ZeroDivisionError:
            return np.nan

    def getHeaderEntry(self) -> Dict[str, Any]:
        return {
            'dist_sample_det': self.dist_sample_det[0],
            'dist_sample_det.err': self.dist_sample_det[1],
            'dist_source_ph1': self.sourcetoph1,
            'dist_ph1_ph2': self.l1,
            'dist_ph2_ph3': self.l2,
            'dist_ph3_sample': self.ph3tosample,
            'dist_det_beamstop': self.beamstoptodetector,
            'pinhole_1': self.pinhole1,
            'pinhole_2': self.pinhole2,
            'pinhole_3': self.pinhole3,
            'description': self.description,
            'beamstop': self.beamstop,
            'wavelength': self.wavelength[0],
            'wavelength.err': self.wavelength[1],
            'beamposx': self.beamposx[0],
            'beamposy': self.beamposy[0],
            'beamposx.err': self.beamposx[1],
            'beamposy.err': self.beamposy[1],
            'mask': self.mask,
            'dist_sample_det.val': self.dist_sample_det[0],
            'pixelsize': self.pixelsize[0],
            'pixelsize.err': self.pixelsize[1],
            'truedistance': self.dist_sample_det[0],  # should be overridden when information on the sample is ready
            'truedistance.err': self.dist_sample_det[1],  # should be overridden when information on the sample is ready
        }  # other fields: truedistance, truedistance.err

    def __eq__(self, other: "GeometryPreset") -> bool:
        logger.debug('Comparing two presets.')
        if not isinstance(other, type(self)):
            logger.debug('Not the same type')
            raise TypeError(type(other))
        if missingkeys := [key for key in self._state if key not in other._state]:
            logger.debug(f'Keys missing from the other: {missingkeys}')
            return False
        elif missingkeys := [key for key in other._state if key not in self._state]:
            logger.debug(f'Keys missing from this: {missingkeys}')
            return False
        else:
            for key in self._state:
                thisvalue = self._state[key]
                othervalue = other._state[key]
                if not isinstance(thisvalue, type(othervalue)):
                    # types are different
                    logger.debug(f'Types of key {key} in this ({type(thisvalue)}) and other ({type(othervalue)}) are different.')
                    return False
                elif isinstance(thisvalue, (float, str)) and thisvalue != othervalue:
                    logger.debug(f'The value of key {key} in this ({thisvalue}) and other ({othervalue}) is different')
                    return False
                elif isinstance(thisvalue, (tuple, list, set, dict)) and len(thisvalue) != len(othervalue):
                    logger.debug(f'The length of key {key} in this ({len(thisvalue)}) and other ({len(othervalue)}) is different')
                    return False
                elif isinstance(thisvalue, tuple) and any([t != o for t, o in zip(thisvalue, othervalue)]):
                    logger.debug(f'The elements of key {key} in this ({thisvalue}) and other ({othervalue}) are different')
                    return False
                elif isinstance(thisvalue, list) and any(
                        [t != o for t, o in zip(sorted(thisvalue), sorted(othervalue))]):
                    return False
                # ToDo: set, dict
            logger.debug('The two presets are equal.')
            return True
