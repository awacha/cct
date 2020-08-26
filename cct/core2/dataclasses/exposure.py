import enum
from typing import Optional, Union

import numpy as np

from .curve import Curve
from .header import Header
from ..algorithms.radavg import radavg, autoq


class ErrorPropagationType(enum.Enum):
    IndependentSamplesOfTheSameQuantity = 0
    Linear = 1
    Squared = 2
    SquaredOrRMS = 3


class Exposure:
    intensity: np.ndarray
    mask: np.ndarray
    uncertainty: np.ndarray
    header: Header

    def __init__(self, intensity: np.ndarray, header: Header, uncertainty: Optional[np.ndarray] = None,
                 mask: Optional[np.ndarray] = None):
        self.intensity = intensity
        if uncertainty is None:
            uncertainty = np.zeros_like(self.intensity)
        if mask is None:
            mask = np.ones(self.intensity.shape, np.uint8)
        else:
            mask = mask.astype(np.uint8)
        if (intensity.shape != uncertainty.shape) or (intensity.shape != mask.shape):
            raise ValueError('Shape mismatch')
        self.mask = mask
        self.uncertainty = uncertainty
        self.header = header

    def radial_average(self, qbincenters: Optional[Union[np.ndarray, int]],
                       errorprop: ErrorPropagationType = ErrorPropagationType.SquaredOrRMS,
                       qerrorprop: ErrorPropagationType = ErrorPropagationType.SquaredOrRMS) -> Curve:
        if (qbincenters is None) or isinstance(qbincenters, int):
            qbincenters = autoq(
                self.mask, self.header.wavelength[0], self.header.distance[0], self.header.pixelsize[0],
                self.header.beamposrow[0], self.header.beamposcol[0], linspacing=True,
                N=-1 if qbincenters is None else qbincenters)
        q, intensity, uncertainty, quncertainty, binarea, pixel = radavg(
            self.intensity, self.uncertainty, self.mask,
            self.header.wavelength[0], self.header.wavelength[1],
            self.header.distance[0], self.header.distance[1],
            self.header.pixelsize[0], self.header.pixelsize[1],
            self.header.beamposrow[0], self.header.beamposrow[1],
            self.header.beamposcol[0], self.header.beamposcol[1],
            qbincenters,
            errorprop.value, qerrorprop.value
        )
        return Curve.fromVectors(q, intensity, uncertainty, quncertainty, binarea, pixel)

    def __iadd__(self, other):
        pass

    def __add__(self, other):
        pass

    def __sub__(self, other):
        pass
