from typing import Optional

import numpy as np


class Curve:
    _data: np.ndarray

    def __init__(self):
        pass

    @property
    def q(self) -> np.ndarray:
        return self._data[:, 0]

    @property
    def intensity(self) -> np.ndarray:
        return self._data[:, 1]

    @property
    def uncertainty(self) -> np.ndarray:
        return self._data[:, 2]

    @property
    def quncertainty(self) -> np.ndarray:
        return self._data[:, 3]

    @property
    def binarea(self) -> np.ndarray:
        return self._data[:, 4]

    @property
    def pixel(self) -> np.ndarray:
        return self._data[:, 5]

    @classmethod
    def fromFile(cls, filename: str, *args, **kwargs) -> "Curve":
        data = np.loadtxt(filename, *args, **kwargs)
        self = cls()
        self._data = np.empty((data.shape[0], 6)) * np.nan
        self._data[:, :min(data.shape[1], 6)] = data[:, :min(data.shape[1], 6)]
        return self

    @classmethod
    def fromArray(cls, array: np.ndarray) -> "Curve":
        self = cls()
        self._data = array
        return self

    @classmethod
    def fromVectors(cls, q: np.ndarray, intensity: np.ndarray, uncertainty: Optional[np.ndarray] = None,
                    quncertainty: Optional[np.ndarray] = None, binarea: Optional[np.ndarray] = None,
                    pixel: Optional[np.ndarray] = None) -> "Curve":
        assert (q is not None) and (intensity is not None)
        if not all([
            q.ndim == 1,
            intensity.ndim == 1,
            (uncertainty is None) or (uncertainty.ndim == 1),
            (quncertainty is None) or (quncertainty.ndim == 1),
            (binarea is None) or (binarea.ndim == 1),
            (pixel is None) or (pixel.ndim == 1)
        ]):
            raise ValueError('Supplied arrays must be one-dimensional.')
        if not all([
            len(intensity) == len(q),
            (uncertainty is None) or (len(uncertainty) == len(q)),
            (quncertainty is None) or (len(quncertainty) == len(q)),
            (binarea is None) or (len(binarea) == len(q)),
            (pixel is None) or (len(pixel) == len(q))
        ]):
            raise ValueError('All vectors must have the same length.')
        self = cls()
        self._data = np.empty((len(q), 6))
        self._data[:, 0] = q
        self._data[:, 1] = intensity
        self._data[:, 2] = uncertainty if uncertainty is not None else np.nan
        self._data[:, 3] = quncertainty if quncertainty is not None else np.nan
        self._data[:, 4] = binarea if binarea is not None else np.nan
        self._data[:, 5] = pixel if pixel is not None else np.nan
        return self

    def trim(self, left: float = -np.inf, right: float = np.inf, bottom=-np.inf, top=np.inf, bypixel: bool = False):
        if bypixel:
            xtrimidx = np.logical_and(self._data[:, 5] <= right, self._data[:, 5] >= left)
        else:
            xtrimidx = np.logical_and(self._data[:, 0] <= right, self._data[:, 0] >= left)
        ytrimidx = np.logical_and(self._data[:, 1] <= top, self._data[:, 1] >= bottom)
        curve = Curve()
        curve._data = self._data[np.logical_and(xtrimidx, ytrimidx)]
        return curve

    def __len__(self) -> int:
        return self._data.shape[0]

    def sanitize(self) -> "Curve":
        idx = np.logical_and(np.isfinite(self.q), np.isfinite(self.intensity))
        idx = np.logical_and(idx, self.q > 0)
        for vector in [self.uncertainty, self.quncertainty, self.pixel]:
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
        return Curve.fromArray(self._data[idx, :])
