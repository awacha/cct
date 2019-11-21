from typing import Tuple

import numpy as np


class MatrixAverager:
    value: np.ndarray = None
    value2: np.ndarray = None
    error: np.ndarray = None
    count: int = 0
    method: str

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

    def __init__(self, errorpropagationmethod:str):
        if errorpropagationmethod in ['Weighted', 'Average', 'Squared (Gaussian)', 'Conservative']:
            self.method = errorpropagationmethod
        else:
            raise ValueError('Invalid error propagation method: {}'.format(errorpropagationmethod))

    def add(self, value:np.ndarray, error:np.ndarray):
        error = self.fixBadValues(error)
        if self.value is None:
            if self.method == 'Weighted':
                self.value = value/error**2
                self.error = 1/error**2
            elif self.method == 'Average':
                self.error = error*1  # Multiplication by 1: make a copy
                self.value = value*1  # Multiplication by 1: make a copy
            elif self.method == 'Squared (Gaussian)':
                self.error = error**2
                self.value = value*1  # Multiplication by 1: make a copy
            elif self.method == 'Conservative':
                self.error = error**2
                self.value = value *1  # Multiplication by 1: make a copy
                self.value2 = value**2
        else:
            if self.method == 'Weighted':
                self.value += value/error**2
                self.error += 1/error**2
            elif self.method == 'Average':
                self.error += error
                self.value += value
            elif self.method == 'Squared (Gaussian)':
                self.error += error**2
                self.value += value
            elif self.method == 'Conservative':
                self.value += value
                self.error += error**2
                self.value2 += value**2
        self.count +=1

    def get(self) -> Tuple[np.ndarray, np.ndarray]:
        if self.method == 'Weighted':
            return self.value / self.error, 1/self.error**0.5
        elif self.method == 'Average':
            return self.value / self.count, self.error/self.count**2
        elif self.method == 'Squared (Gaussian)':
            return self.value / self.count, self.error**0.5/self.count
        elif self.method == 'Conservative':
            error_std = (self.value2 - self.value ** 2 / self.count) / (
                    self.count - 1) / self.count ** 0.5 if self.count > 1 else np.zeros_like(self.value)
            error_propagated = self.error ** 0.5 / self.count
            return self.value / self.count, np.stack((error_std, error_propagated)).max(axis=0)

    @staticmethod
    def fixBadValues(matrix: np.ndarray) -> np.ndarray:
        """replace NaNs and nonpositive values with the smallest positive value"""
        bad = ~np.logical_and(np.isfinite(matrix), matrix > 0)
        if bad.sum() >= matrix.size:
            return np.ones_like(matrix)
        matrix = matrix.copy()
        matrix[bad] = np.min(matrix[~bad])
        return matrix
