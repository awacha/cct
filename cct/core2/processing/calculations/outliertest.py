import enum
import logging
from collections import namedtuple
from typing import Optional, Tuple, Sequence

import numpy as np
import scipy.stats

from ...algorithms.correlmatrix import correlmatrix_cython
from ...algorithms.schilling import cormap_pval, longest_run

SchillingResult = namedtuple('SchillingResult', ('statistic', 'pvalue'))

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
    fsns: Optional[np.ndarray] = None

    def __init__(self, method: OutlierMethod, threshold: float, curves: Optional[np.ndarray] = None,
                 correlmatrix: Optional[np.ndarray] = None, fsns: Optional[Sequence[int]] = None):
        if curves is not None:
            self.correlmatrix = correlmatrix_cython(curves[:, 1, :], curves[:, 2, :])
        elif correlmatrix is not None:
            self.correlmatrix = correlmatrix
        else:
            raise ValueError('Either `curves` or `correlmatrix` argument is needed.')
        self.score = np.diagonal(self.correlmatrix)
        self.method = method
        self.threshold = threshold
        self.outlierverdict = np.zeros(self.score.shape, np.bool)
        if fsns is not None:
            self.fsns = np.array(fsns)
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
        if self.correlmatrix.shape[0] < 3:
            logger.warning('Cannot do outlier detection for less than 3 measurements.')
            return np.zeros(self.score.shape, dtype=np.bool)
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
        return scipy.stats.shapiro(self.score)

    def outlierindices(self) -> np.ndarray:
        return np.arange(len(self.score))[self.outlierverdict]

    def schillingTest(self):
        longestrun = longest_run(self.score - np.nanmean(self.score))
        p = cormap_pval(self.score.size, longestrun)
        return SchillingResult(longestrun, p)
