from typing import Optional, Union, Tuple, Iterable
import logging

import numpy as np

from .curve import Curve
from .azimuthalcurve import AzimuthalCurve
from .header import Header
from ..algorithms.matrixaverager import ErrorPropagationMethod, MatrixAverager
from ..algorithms.radavg import radavg, autoq, azimavg

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Exposure:
    intensity: np.ndarray
    mask: np.ndarray  # 1: valid: 0: invalid
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

    def radial_average(self, qbincenters: Optional[Union[np.ndarray, int]] = None,
                       errorprop: ErrorPropagationMethod = ErrorPropagationMethod.Conservative,
                       qerrorprop: ErrorPropagationMethod = ErrorPropagationMethod.Conservative) -> Curve:
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

    def azim_average(self, count=100,
                     errorprop: ErrorPropagationMethod = ErrorPropagationMethod.Conservative,
                     qerrorprop: ErrorPropagationMethod = ErrorPropagationMethod.Conservative) -> AzimuthalCurve:
        phi, intensity, uncertainty, phiuncertainty, binarea, qmean, qstd = azimavg(
            self.intensity, self.uncertainty, self.mask,
            self.header.wavelength[0],  # self.header.wavelength[1],
            self.header.distance[0],  # self.header.distance[1],
            self.header.pixelsize[0],  # self.header.pixelsize[1],
            self.header.beamposrow[0], self.header.beamposrow[1],
            self.header.beamposcol[0], self.header.beamposcol[1],
            count,
            errorprop.value, qerrorprop.value
        )
        return AzimuthalCurve.fromVectors(phi, intensity, uncertainty, phiuncertainty, binarea, qmean, qstd)

    @property
    def size(self) -> int:
        return self.intensity.size

    @property
    def shape(self) -> Tuple[int, ...]:
        return self.intensity.shape

    def radius_pixel(self) -> Tuple[np.ndarray, np.ndarray]:
        row = np.arange(self.intensity.shape[0])[:, np.newaxis] - self.header.beamposrow[0]
        drow = self.header.beamposrow[1]
        col = np.arange(self.intensity.shape[1])[np.newaxis, :] - self.header.beamposcol[0]
        dcol = self.header.beamposcol[1]
        radius = (row ** 2 + col ** 2) ** 0.5
        dradius = (row ** 2 * drow ** 2 + col ** 2 * dcol ** 2) ** 0.5 / radius
        return radius, dradius

    def radius_distance(self) -> Tuple[np.ndarray, np.ndarray]:
        r, dr = self.radius_pixel()
        return (r * self.header.pixelsize[0],
                (dr ** 2 * self.header.pixelsize[0] ** 2 + r ** 2 * self.header.pixelsize[1] ** 2) ** 0.5)

    def twotheta(self) -> Tuple[np.ndarray, np.ndarray]:
        r, dr = self.radius_distance()
        tan2th = (
            r / self.header.distance[0],
            (r ** 2 * self.header.distance[1] ** 2 / self.header.distance[0] ** 4 + dr ** 2 / self.header.distance[
                0] ** 2) ** 0.5
        )
        return (np.arctan(tan2th[0]),
                np.abs(tan2th[1] / (1 + tan2th[0] ** 2)))

    def q(self) -> Tuple[np.ndarray, np.ndarray]:
        tth, dtth = self.twotheta()
        th, dth = 0.5 * tth, 0.5 * dtth
        sinth = np.sin(th), np.abs(dth * np.cos(th))
        return (4 * np.pi * sinth[0] / self.header.wavelength[0],
                4 * np.pi * (
                        sinth[1] ** 2 / self.header.wavelength[0] + sinth[0] ** 2 * self.header.wavelength[1] ** 2 /
                        self.header.wavelength[0] ** 4) ** 0.5)

    def save(self, filename: str):
        np.savez_compressed(filename, Intensity=self.intensity, Error=self.uncertainty, mask=self.mask)

    @classmethod
    def average(cls, exposures: Iterable["Exposure"], errorpropagation: ErrorPropagationMethod) -> "Exposure":
        avgintensity = MatrixAverager(errorpropagation)
        mask = None
        headers=[]
        for ex in exposures:
            assert ex.intensity is not None
            assert ex.uncertainty is not None
            avgintensity.add(ex.intensity, ex.uncertainty)
            if mask is None:
                mask = ex.mask
            else:
                mask = np.logical_and(mask > 0, ex.mask > 0)
            headers.append(ex.header)
        intensity, uncertainty = avgintensity.get()
        return Exposure(intensity, Header.average(*headers), uncertainty, mask)

    def qtopixel(self, q: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        return np.tan(2 * np.arcsin(q / 4 / np.pi * self.header.wavelength[0])) * self.header.distance[0] / \
               self.header.pixelsize[0]

    def pixeltoq(self, pixel: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        return 4 * np.pi * np.sin(0.5 * np.arctan(pixel * self.header.pixelsize[0] / self.header.distance[0])) / \
               self.header.wavelength[0]
