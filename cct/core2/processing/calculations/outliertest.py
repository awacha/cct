import enum
import logging
import time
from typing import Dict, Callable, Optional, Tuple
import scipy.stats
from ...algorithms.correlmatrix import correlmatrix_cython

import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class OutlierMethod(enum.Enum):
    ZScore = 'Z-score'
    ZScoreMod = 'Modified Z-score'
    IQR = 'Interquartile Range'


class OutlierTest:
    score: np.ndarray
    method: OutlierMethod
    threshold: float
    outlierverdict: np.ndarray
    correlmatrix: np.ndarray

    def __init__(self, curves: np.ndarray, method:OutlierMethod, threshold: float):
        self.correlmatrix = correlmatrix_cython(curves[:,1,:], curves[:,2,:])
        self.score = np.diagonal(self.correlmatrix)
        self.method = method
        self.threshold = threshold
        self.outlierverdict = np.zeros(self.score.shape, np.bool)
        self.markOutliers()

    def acceptanceInterval(self) -> Tuple[float, float]:
        if self.method in [OutlierMethod.ZScore, OutlierMethod.ZScoreMod]:
            return -self.threshold, self.threshold
        elif self.method == OutlierMethod.IQR:
            q1, q3 = np.percentile(self.score, [25, 75])
            iqr = q3 - q1
            return q1 - iqr * self.threshold, q3 + iqr * self.threshold
        else:
            assert False

    def markOutliers(self) -> np.ndarray:
        if self.method == OutlierMethod.ZScore:
            self.outlierverdict = (np.abs(self.score - np.nanmean(self.score)) / np.nanstd(self.score)) > self.threshold
        elif self.method == OutlierMethod.ZScoreMod:
            centered = self.score - np.nanmedian(self.score)
            self.outlierverdict = np.abs(0.6745 * centered / np.nanmedian(np.abs(centered))) > self.threshold
        elif self.method == OutlierMethod.IQR:
            q1, q3 = np.percentile(self.score, [25, 75])
            iqr = q3 - q1
            self.outlierverdict = np.logical_or(
                self.score < q1 - (iqr * self.threshold),
                self.score > q3 + (iqr * self.threshold))
        else:
            assert False
        return self.outlierverdict

    def shapiroTest(self) -> scipy.stats.morestats.ShapiroResult:
        return scipy.stats.shapiro(self.score[self.outlierverdict])

    def outlierindices(self) ->  np.ndarray:
        return np.arange(len(self.score))[self.outlierverdict]
