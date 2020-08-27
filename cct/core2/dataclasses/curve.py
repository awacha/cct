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
            (uncertainty.ndim == 1) or uncertainty is None,
            (quncertainty.ndim == 1) or quncertainty is None,
            (binarea.ndim == 1) or binarea is None,
            (pixel.ndim == 1) or pixel is None
        ]):
            raise ValueError('Supplied arrays must be one-dimensional.')
        if not all([
            len(intensity) == len(q),
            (len(uncertainty) == len(q)) or uncertainty is None,
            (len(quncertainty) == len(q)) or quncertainty is None,
            (len(binarea) == len(q)) or binarea is None,
            (len(pixel) == len(q)) or pixel is None
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