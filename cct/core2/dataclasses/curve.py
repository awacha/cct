import numbers
from typing import Optional, Iterable, Tuple, Union

import numpy as np

from ..algorithms.matrixaverager import MatrixAverager, ErrorPropagationMethod


class Curve:
    _data: np.ndarray

    def __init__(self):
        pass

    @property
    def q(self) -> np.ndarray:
        return self._data[:, 0]

    @q.setter
    def q(self, newvalue):
        self._data[:, 0] = newvalue

    @property
    def intensity(self) -> np.ndarray:
        return self._data[:, 1]

    @intensity.setter
    def intensity(self, newvalue):
        self._data[:, 1] = newvalue

    @property
    def uncertainty(self) -> np.ndarray:
        return self._data[:, 2]

    @uncertainty.setter
    def uncertainty(self, newvalue):
        self._data[:, 2] = newvalue

    @property
    def quncertainty(self) -> np.ndarray:
        return self._data[:, 3]

    @quncertainty.setter
    def quncertainty(self, newvalue):
        self._data[:, 3] = newvalue

    @property
    def binarea(self) -> np.ndarray:
        return self._data[:, 4]

    @binarea.setter
    def binarea(self, newvalue):
        self._data[:, 4] = newvalue

    @property
    def pixel(self) -> np.ndarray:
        return self._data[:, 5]

    @pixel.setter
    def pixel(self, newvalue):
        self._data[:, 5] = newvalue

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
        self._data = np.empty((array.shape[0], 6), array.dtype) + np.nan
        self._data[:, :array.shape[1]] = array
        return self

    def __array__(self) -> np.ndarray:
        return self._data

    asArray = __array__

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
        return Curve.fromArray(self._data[self.isvalid(), :])

    @classmethod
    def average(cls, curves: Iterable["Curve"], ierrorpropagation: ErrorPropagationMethod,
                qerrorpropagation: ErrorPropagationMethod) -> "Curve":
        qavg = MatrixAverager(errorpropagationmethod=qerrorpropagation)
        iavg = MatrixAverager(errorpropagationmethod=ierrorpropagation)
        aavg = MatrixAverager(errorpropagationmethod=ierrorpropagation)
        pavg = MatrixAverager(errorpropagationmethod=ierrorpropagation)
        for c in curves:
            qavg.add(c.q, c.quncertainty)
            iavg.add(c.intensity, c.uncertainty)
            aavg.add(c.binarea, c.binarea)
            pavg.add(c.pixel, c.pixel)
        q, dq = qavg.get()
        i, di = iavg.get()
        a = aavg.get()[0]
        p = pavg.get()[0]
        return Curve.fromVectors(q, i, di, dq, a, p)

    def isfinite(self) -> np.ndarray:
        idx = np.logical_and(np.isfinite(self.q, np.isfinite(self.intensity)))
        for vector in [self.uncertainty, self.quncertainty, self.pixel, self.binarea]:
            if np.isfinite(vector).sum() > 0:  # if not all elements are NaN
                idx = np.logical_and(idx, np.isfinite(vector))
        return idx

    def isvalid(self) -> np.ndarray:
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
        return idx

    def __getitem__(self, item) -> "Curve":
        if isinstance(item, np.ndarray) and (item.dtype == bool):
            return Curve.fromArray(self._data[item, :])

    def _checkcompatibility(self, other: "Curve", maxdifferenceratio: float = 0.005):
        incompatibility = np.abs(self.q - other.q) / np.max(np.mean((self.q, other.q)), axis=0) * 2
        if np.any(incompatibility[np.isfinite(incompatibility)] > maxdifferenceratio):  # 0.01 means 1%
            raise ValueError(
                f'The two q-scales are incompatible. Max. incompatibility: {incompatibility[np.isfinite(incompatibility)].max()}')

    def __sub__(self, other: Union["Curve", numbers.Real, Tuple[numbers.Real, numbers.Real]]) -> "Curve":
        if isinstance(other, Curve):
            self._checkcompatibility(other)
            return self.fromVectors(
                q=0.5 * (self.q + other.q),
                intensity=self.intensity - other.intensity,
                uncertainty=(self.uncertainty ** 2 + other.uncertainty ** 2) ** 0.5,
                quncertainty=(self.quncertainty ** 2 + other.quncertainty ** 2) ** 0.5 / 2.0,
                binarea=None,
                pixel=None
            )
        elif isinstance(other, numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity - other,
                uncertainty=self.uncertainty,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        elif isinstance(other, tuple) and (len(other) == 2) and isinstance(other[0], numbers.Real) and isinstance(
                other[1], numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity - other[0],
                uncertainty=(self.uncertainty ** 2 + other[1] ** 2) ** 0.5,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        else:
            return NotImplemented

    def __add__(self, other: Union["Curve", numbers.Real, Tuple[numbers.Real, numbers.Real]]) -> "Curve":
        if isinstance(other, Curve):
            self._checkcompatibility(other)
            return self.fromVectors(
                q=0.5 * (self.q + other.q),
                intensity=self.intensity + other.intensity,
                uncertainty=(self.uncertainty ** 2 + other.uncertainty ** 2) ** 0.5,
                quncertainty=(self.quncertainty ** 2 + other.quncertainty ** 2) ** 0.5 / 2.0,
                binarea=None,
                pixel=None
            )
        elif isinstance(other, numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity + other,
                uncertainty=self.uncertainty,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        elif isinstance(other, tuple) and (len(other) == 2) and isinstance(other[0], numbers.Real) and isinstance(
                other[1], numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity + other[0],
                uncertainty=(self.uncertainty ** 2 + other[1] ** 2) ** 0.5,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        else:
            return NotImplemented

    def __rsub__(self, other: Union[numbers.Real, Tuple[numbers.Real, numbers.Real]]) -> "Curve":
        if isinstance(other, numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=other - self.intensity,
                uncertainty=self.uncertainty,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        elif isinstance(other, tuple) and (len(other) == 2) and isinstance(other[0], numbers.Real) and isinstance(
                other[1], numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=other[0] - self.intensity,
                uncertainty=(self.uncertainty ** 2 + other[1] ** 2) ** 0.5,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        else:
            return NotImplemented

    def __radd__(self, other: Union[numbers.Real, Tuple[numbers.Real, numbers.Real]]) -> "Curve":
        if isinstance(other, numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity + other,
                uncertainty=self.uncertainty,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        elif isinstance(other, tuple) and (len(other) == 2) and isinstance(other[0], numbers.Real) and isinstance(
                other[1], numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity + other[0],
                uncertainty=(self.uncertainty ** 2 + other[1] ** 2) ** 0.5,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        else:
            return NotImplemented

    def __truediv__(self, other: Union["Curve", numbers.Real, Tuple[numbers.Real, numbers.Real]]) -> "Curve":
        if isinstance(other, Curve):
            self._checkcompatibility(other)
            return self.fromVectors(
                q=0.5 * (self.q + other.q),
                intensity=self.intensity / other.intensity,
                uncertainty=(
                                    self.uncertainty ** 2 / other.intensity ** 2 + other.uncertainty ** 2 * self.intensity ** 2 / other.intensity ** 4) ** 0.5,
                quncertainty=(self.quncertainty ** 2 + other.quncertainty ** 2) ** 0.5 / 2.0,
                binarea=None,
                pixel=None
            )
        elif isinstance(other, numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity / other,
                uncertainty=np.abs(self.uncertainty / other),
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        elif isinstance(other, tuple) and (len(other) == 2) and isinstance(other[0], numbers.Real) and isinstance(
                other[1], numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity / other[0],
                uncertainty=(self.uncertainty ** 2 / other[0] ** 2 + other[1] ** 2 * self.intensity ** 2 / other[
                    0] ** 4) ** 0.5,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        else:
            return NotImplemented

    def __mul__(self, other: Union["Curve", numbers.Real, Tuple[numbers.Real, numbers.Real]]) -> "Curve":
        if isinstance(other, Curve):
            self._checkcompatibility(other)
            return self.fromVectors(
                q=0.5 * (self.q + other.q),
                intensity=self.intensity * other.intensity,
                uncertainty=(
                                    self.uncertainty ** 2 * other.intensity ** 2 + other.uncertainty ** 2 * self.intensity ** 2) ** 0.5,
                quncertainty=(self.quncertainty ** 2 + other.quncertainty ** 2) ** 0.5 / 2.0,
                binarea=None,
                pixel=None
            )
        elif isinstance(other, numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity * other,
                uncertainty=np.abs(self.uncertainty * other),
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        elif isinstance(other, tuple) and (len(other) == 2) and isinstance(other[0], numbers.Real) and isinstance(
                other[1], numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity * other[0],
                uncertainty=(self.uncertainty ** 2 * other[0] ** 2 + self.intensity ** 2 * other[1] ** 2) ** 0.5,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        else:
            return NotImplemented

    def __rtruediv__(self, other: Union[numbers.Real, Tuple[numbers.Real, numbers.Real]]) -> "Curve":
        if isinstance(other, numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=other / self.intensity,
                uncertainty=np.abs(other * self.uncertainty / self.intensity ** 2),
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        elif isinstance(other, tuple) and (len(other) == 2) and isinstance(other[0], numbers.Real) and isinstance(
                other[1], numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=other[0] / self.intensity,
                uncertainty=(self.uncertainty ** 2 / self.intensity ** 4 * other[0] ** 2 + other[
                    1] ** 2 / self.intensity ** 2) ** 0.5,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        else:
            return NotImplemented

    def __rmul__(self, other: Union[numbers.Real, Tuple[numbers.Real, numbers.Real]]) -> "Curve":
        if isinstance(other, numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity * other,
                uncertainty=np.abs(self.uncertainty * other),
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        elif isinstance(other, tuple) and (len(other) == 2) and isinstance(other[0], numbers.Real) and isinstance(
                other[1], numbers.Real):
            return self.fromVectors(
                q=self.q,
                intensity=self.intensity * other[0],
                uncertainty=(self.uncertainty ** 2 * other[0] ** 2 + self.intensity ** 2 * other[1] ** 2) ** 0.5,
                quncertainty=self.quncertainty,
                binarea=self.binarea,
                pixel=self.pixel
            )
        else:
            return NotImplemented
