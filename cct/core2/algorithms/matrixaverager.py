import enum
import logging
from typing import Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ErrorPropagationMethod(enum.Enum):
    # Error propagation types: if y_i are the measured data and e_i are their uncertainties:
    #
    #  1) Weighted:
    #       y = sum_i (1/e_i^2 y_i) / sum_i (1/e_i^2)
    #       e = 1/sqrt(sum_i(1/e_i^2))
    #  2) Average of errors (linear):
    #       y = mean(y_i)    ( simple mean)
    #       e = mean(e_i)
    #  3) Gaussian (squared):
    #       y = mean(y_i)
    #       e = sqrt(sum(e_i^2)/N)
    #  4) Conservative:
    #       y = mean(y_i)
    #       e: either the Gaussian, or that from the standard deviation, take the larger one.
    Weighted = 0
    Linear = 1
    Gaussian = 2
    Conservative = 3
    StandardErrorOfTheMean = 4


class MatrixAverager:
    value: Optional[np.ndarray] = None
    value2: Optional[np.ndarray] = None
    error: Optional[np.ndarray] = None
    count: int = 0
    method: ErrorPropagationMethod

    def __init__(self, errorpropagationmethod: ErrorPropagationMethod):
        self.method = errorpropagationmethod
        self.count = 0

    def add(self, value: np.ndarray, error: np.ndarray):
        error = self.fixBadValues(error)
        if self.value is None:
            assert (self.value2 is None) and (self.error is None)
            if self.method == ErrorPropagationMethod.Weighted:
                self.value = value / error ** 2
                self.error = 1 / error ** 2
            elif self.method == ErrorPropagationMethod.Linear:
                self.error = error * 1  # Multiplication by 1: make a copy
                self.value = value * 1  # Multiplication by 1: make a copy
            elif self.method == ErrorPropagationMethod.Gaussian:
                self.error = error ** 2
                self.value = value * 1  # Multiplication by 1: make a copy
            elif self.method == ErrorPropagationMethod.Conservative:
                self.error = error ** 2
                self.value = value * 1  # Multiplication by 1: make a copy
                self.value2 = value ** 2
            elif self.method == ErrorPropagationMethod.StandardErrorOfTheMean:
                self.error = error  # don't use it
                self.value = value * 1
                self.value2 = value ** 2
        else:
            if self.method == ErrorPropagationMethod.Weighted:
                self.value += value / error ** 2
                self.error += 1 / error ** 2
            elif self.method == ErrorPropagationMethod.Linear:
                self.error += error
                self.value += value
            elif self.method == ErrorPropagationMethod.Gaussian:
                self.error += error ** 2
                self.value += value
            elif self.method == ErrorPropagationMethod.Conservative:
                self.value += value
                self.error += error ** 2
                self.value2 += value ** 2
            elif self.method == ErrorPropagationMethod.StandardErrorOfTheMean:
                self.value += value
                self.value2 += value ** 2
        self.count += 1

    def get(self) -> Tuple[np.ndarray, np.ndarray]:
        if not self.count:
            raise ValueError('Cannot get average: no data given yet.')
        logger.debug(f'Returning averaged matrices according to method {self.method}. {self.count=}')
        assert self.value is not None
        assert self.error is not None
        if self.method == ErrorPropagationMethod.Weighted:
            return self.value / self.error, 1 / self.error ** 0.5
        elif self.method == ErrorPropagationMethod.Linear:
            return self.value / self.count, self.error / self.count ** 2
        elif self.method == ErrorPropagationMethod.Gaussian:
            return self.value / self.count, self.error ** 0.5 / self.count
        elif self.method == ErrorPropagationMethod.Conservative:
            # Standard error of the mean or propagated error, whichever is largest
            error_sem = ((self.value2 - self.value ** 2 / self.count) / (
                    self.count - 1)) ** 0.5 / self.count ** 0.5 if self.count > 1 else np.zeros_like(self.value)
            error_propagated = self.error ** 0.5 / self.count
            return self.value / self.count, np.stack((error_sem, error_propagated)).max(axis=0)
        elif self.method == ErrorPropagationMethod.StandardErrorOfTheMean:
            return self.value / self.count, \
                   ((1 / (self.count - 1) / self.count * (self.value2 - self.value ** 2 / self.count)) ** 0.5) \
                       if self.count > 1 else np.zeros_like(self.value)

    @staticmethod
    def fixBadValues(matrix: np.ndarray) -> np.ndarray:
        """replace NaNs and nonpositive values with the smallest positive value"""
        bad = ~np.logical_and(np.isfinite(matrix), matrix > 0)
        nbad = bad.sum()
        if not nbad:
            return matrix
        elif nbad >= matrix.size:
            return np.ones_like(matrix)
        else:
            matrix = matrix.copy()
            matrix[bad] = np.min(matrix[~bad])
            return matrix
