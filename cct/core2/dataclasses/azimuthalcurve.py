from typing import Optional, Iterable

import numpy as np

from ..algorithms.matrixaverager import MatrixAverager, ErrorPropagationMethod


class AzimuthalCurve:
    _data: np.ndarray

    def __init__(self):
        pass

    @property
    def phi(self) -> np.ndarray:
        return self._data[:, 0]

    @property
    def intensity(self) -> np.ndarray:
        return self._data[:, 1]

    @property
    def uncertainty(self) -> np.ndarray:
        return self._data[:, 2]

    @property
    def phiuncertainty(self) -> np.ndarray:
        return self._data[:, 3]

    @property
    def binarea(self) -> np.ndarray:
        return self._data[:, 4]

    @property
    def qmean(self) -> np.ndarray:
        return self._data[:, 5]

    @property
    def qstd(self) -> np.ndarray:
        return self._data[:, 5]

    @classmethod
    def fromFile(cls, filename: str, *args, **kwargs) -> "AzimuthalCurve":
        data = np.loadtxt(filename, *args, **kwargs)
        self = cls()
        self._data = np.empty((data.shape[0], 7)) * np.nan
        self._data[:, :min(data.shape[1], 7)] = data[:, :min(data.shape[1], 7)]
        return self

    @classmethod
    def fromArray(cls, array: np.ndarray) -> "AzimuthalCurve":
        self = cls()
        self._data = np.empty((array.shape[0], 7), array.dtype) + np.nan
        self._data[:, :array.shape[1]] = array
        return self

    def __array__(self) -> np.ndarray:
        return self._data

    asArray = __array__

    @classmethod
    def fromVectors(cls, phi: np.ndarray, intensity: np.ndarray, uncertainty: Optional[np.ndarray] = None,
                    phiuncertainty: Optional[np.ndarray] = None, binarea: Optional[np.ndarray] = None,
                    qmean: Optional[np.ndarray] = None, qstd: Optional[np.ndarray] = None) -> "AzimuthalCurve":
        assert (phi is not None) and (intensity is not None)
        if not all([
            phi.ndim == 1,
            intensity.ndim == 1,
            (uncertainty is None) or (uncertainty.ndim == 1),
            (phiuncertainty is None) or (phiuncertainty.ndim == 1),
            (binarea is None) or (binarea.ndim == 1),
            (qmean is None) or (qmean.ndim == 1),
            (qstd is None) or (qstd.ndim == 1),
        ]):
            raise ValueError('Supplied arrays must be one-dimensional.')
        if not all([
            len(intensity) == len(phi),
            (uncertainty is None) or (len(uncertainty) == len(phi)),
            (phiuncertainty is None) or (len(phiuncertainty) == len(phi)),
            (binarea is None) or (len(binarea) == len(phi)),
            (qmean is None) or (len(qmean) == len(phi)),
            (qstd is None) or (len(qstd) == len(phi)),
        ]):
            raise ValueError('All vectors must have the same length.')
        self = cls()
        self._data = np.empty((len(phi), 7))
        self._data[:, 0] = phi
        self._data[:, 1] = intensity
        self._data[:, 2] = uncertainty if uncertainty is not None else np.nan
        self._data[:, 3] = phiuncertainty if phiuncertainty is not None else np.nan
        self._data[:, 4] = binarea if binarea is not None else np.nan
        self._data[:, 5] = qmean if qmean is not None else np.nan
        self._data[:, 6] = qstd if qstd is not None else np.nan
        return self

    def __len__(self) -> int:
        return self._data.shape[0]

    def sanitize(self) -> "AzimuthalCurve":
        return AzimuthalCurve.fromArray(self._data[self.isvalid(), :])

    @classmethod
    def average(cls, curves: Iterable["AzimuthalCurve"], ierrorpropagation: ErrorPropagationMethod, qerrorpropagation: ErrorPropagationMethod, phierrorpropagation: ErrorPropagationMethod) -> "AzimuthalCurve":
        phiavg = MatrixAverager(errorpropagationmethod=phierrorpropagation)
        iavg = MatrixAverager(errorpropagationmethod=ierrorpropagation)
        aavg = MatrixAverager(errorpropagationmethod=ierrorpropagation)
        qavg = MatrixAverager(errorpropagationmethod=qerrorpropagation)
        for c in curves:
            phiavg.add(c.phi, c.phiuncertainty)
            iavg.add(c.intensity, c.uncertainty)
            aavg.add(c.binarea, c.binarea)
            qavg.add(c.qmean, c.qstd)
        q, dq = qavg.get()
        i, di = iavg.get()
        a = aavg.get()[0]
        phi, dphi = phiavg.get()
        return AzimuthalCurve.fromVectors(phi, i, di, dphi, a, q, dq)

    def isfinite(self) -> np.ndarray:
        idx = np.logical_and(np.isfinite(self.phi, np.isfinite(self.intensity)))
        for vector in [self.uncertainty, self.phiuncertainty, self.qmean, self.qstd, self.binarea]:
            if np.isfinite(vector).sum() > 0:  # if not all elements are NaN
                idx = np.logical_and(idx, np.isfinite(vector))
        return idx

    def isvalid(self) -> np.ndarray:
        idx = np.logical_and(np.isfinite(self.phi), np.isfinite(self.intensity))
        for vector in [self.uncertainty, self.phiuncertainty, self.qmean, self.qstd]:
            if np.isfinite(vector).sum() > 0:
                idx = np.logical_and(
                    idx,
                    np.logical_and(
                        np.isfinite(vector),
                        vector >= 0
                    ))
        if np.isfinite(self.binarea).sum() > 0:
            idx = np.logical_and(
                idx,
                np.logical_and(
                    np.isfinite(self.binarea),
                    self.binarea > 0
                ))
        return idx

    def __getitem__(self, item) -> "AzimuthalCurve":
        if isinstance(item, np.ndarray) and (item.dtype == np.bool):
            return AzimuthalCurve.fromArray(self._data[item, :])

