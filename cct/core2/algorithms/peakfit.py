import enum
from typing import Optional

import numpy as np
import scipy.linalg
import scipy.odr
import scipy.optimize
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_gaussian_fwhm_factor = 2 * (2 * np.log(2)) ** 0.5  # FWHM = _gaussian_fwhm_factor * sigma


def LorentzPeak(x, A, x0, fwhm, y0):
    return A / (1 + (2 * (x - x0) / fwhm) ** 2) + y0


def GaussPeak(x, A, x0, fwhm, y0):
    sigma2 = (fwhm / _gaussian_fwhm_factor) ** 2
    return A / (2 * np.pi * sigma2) ** 0.5 * np.exp(- (x - x0) ** 2 / (2 * sigma2)) + y0


def AsymmetricLorentzPeak(x, A, x0, fwhm1, fwhm2, y0):
    result = np.empty_like(x)
    result[x <= x0] = LorentzPeak(x[x <= x0], A, x0, fwhm1, y0)
    result[x > x0] = LorentzPeak(x[x > x0], A, x0, fwhm2, y0)
    return result


def AsymmetricGaussPeak(x, A, x0, fwhm1, fwhm2, y0):
    result = np.empty_like(x)
    result[x <= x0] = GaussPeak(x[x <= x0], A, x0, fwhm1, y0)
    result[x > x0] = GaussPeak(x[x > x0], A, x0, fwhm2, y0)
    return result


class PeakType(enum.Enum):
    Lorentzian = LorentzPeak
    Gaussian = GaussPeak
    AsymmetricLorentzian = AsymmetricLorentzPeak
    AsymmetricGaussian = AsymmetricGaussPeak


def fitpeak(x: np.ndarray, y: np.ndarray, dy: Optional[np.ndarray], dx: Optional[np.ndarray],
            peaktype: PeakType = PeakType.Lorentzian):
    # guess parameters
    parameter_guess = [
        y.max() - y.min(),  # amplitude
        0.5 * (x.max() + x.min()),  # center
        (x.max() - x.min()),  # FWHM
        y.min(),  # offset
    ]
    bounds = [
        (0, x.min(), 0, -np.inf),  # lower bounds
        (np.inf, x.max(), np.inf, np.inf),  # upper bounds
    ]
    diff_step = [(y.max() - y.min())*1e-4, (x.max()-x.min())*1e-4, (x.max() - x.min())*1e-4, (y.max()-y.min())*1e-4]
    if peaktype in [PeakType.AsymmetricGaussian, PeakType.AsymmetricLorentzian]:
        parameter_guess = parameter_guess[:3] + [parameter_guess[2]] + parameter_guess[3:]
        bounds = [
            bounds[0][:3] + (bounds[0][2],) + bounds[0][3:],
            bounds[1][:3] + (bounds[1][2],) + bounds[1][3:]
        ]
        diff_step = diff_step[:3] + [diff_step[2]] + diff_step[3:]
    if dx is None:
        # do an ordinary least-squares fit with/without error bars
        result = scipy.optimize.least_squares(
            fun=(lambda parameters, x, y, dy: (y - peaktype(x, *parameters)) / dy) if dy is not None else (
                lambda parameters, x, y: y - peaktype(x, *parameters)),
            x0=parameter_guess,
            x_scale='jac',
            diff_step=diff_step,
            bounds=bounds,
            method='trf',
            args=(x, y, dy) if dy is not None else (x, y),
        )
        values = result.x
        _, s, VT = scipy.linalg.svd(result.jac, full_matrices=False)
        threshold = np.finfo(float).eps * max(result.jac.shape) * s[0]
        s = s[s > threshold]
        VT = VT[:s.size]
        try:
            covar = np.dot(VT.T / s ** 2, VT)
        except ValueError:
            covar = np.ones((len(result.x), len(result.x))) * np.nan
        return values, covar, lambda x: peaktype(x, *values)
    elif (dx is not None) and (dy is not None):
        # orthogonal distance least-squares
        model = scipy.odr.Model(lambda params, x: peaktype(x, *params))
        data = scipy.odr.RealData(x, y, dx, dy)
        odr = scipy.odr.ODR(data, model, parameter_guess)
        result = odr.run()
        return result.beta, result.cov_beta, lambda x: peaktype(x, *result.beta)
    else:
        raise ValueError('Cannot fit with x errors present and y errors absent.')
