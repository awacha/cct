import numpy as np
import scipy.optimize

from .momentofinertia import _momentofinertia
from ..radavg import fastradavg, fastazimavg, maskforannulus, maskforsectors


def lorentzian(x, hwhm, position, amplitude, offset):
    return hwhm ** 2 / (hwhm ** 2 + (x - position) ** 2) * amplitude + offset


def lorentziantargetfunc(peakparams, x, y):
    return y - lorentzian(x, peakparams[0], peakparams[1], peakparams[2], peakparams[3])


def powerlawtargetfunc(params, x, y):
    return y - params[0] * x ** params[1]


def peakheight(beampos, matrix, mask, rmin, rmax):
    pixel, intensity, area = fastradavg(matrix, mask, beampos[0], beampos[1], rmin, rmax, 20)
    result = scipy.optimize.least_squares(
        lorentziantargetfunc,
        [(rmax - rmin) * 0.5,
         0.5 * (rmax + rmin),
         intensity.max() - intensity.min(),
         intensity.min()
         ],
        bounds=([0, rmin, 0, -np.inf], [10 * (rmax - rmin), rmax, np.inf, np.inf]),
        args=(pixel, intensity),
    )
    if not result.success:
        return np.nan
    return -(result.x[2] + result.x[3])


def peakwidth(beampos, matrix, mask, rmin, rmax):
    pixel, intensity, area = fastradavg(matrix, mask, beampos[0], beampos[1], rmin, rmax, 20)
    result = scipy.optimize.least_squares(
        lorentziantargetfunc,
        [(rmax - rmin) * 0.5,
         0.5 * (rmax + rmin),
         intensity.max() - intensity.min(),
         intensity.min()
         ],
        bounds=([0, rmin, 0, -np.inf], [10 * (rmax - rmin), rmax, np.inf, np.inf]),
        args=(pixel, intensity),
    )
    if not result.success:
        return np.nan
    #    print(beampos, result.x[0])

    return result.x[0]


def slices(beampos, matrix, mask, rmin, rmax):
    N = int(rmax - rmin)
    pixels = np.empty((N, 4))
    intensities = np.empty((N, 4))
    areas = np.empty((N, 4))
    for i in range(4):
        msk = maskforsectors(mask, beampos[0], beampos[1], np.pi * 0.25 + i * np.pi * 0.5, np.pi * 0.25,
                             symmetric=False)
        pixels[:, i], intensities[:, i], areas[:, i] = fastradavg(matrix, msk, beampos[0], beampos[1], rmin, rmax, N)
    valid = areas.prod(axis=1) > 0
    return ((intensities[valid, 0] - intensities[valid, 2]) ** 2 + (
                intensities[valid, 1] - intensities[valid, 3]) ** 2).mean()


def powerlaw(beampos, matrix, mask, rmin, rmax):
    pixel, intensity, area = fastradavg(matrix, mask, beampos[0], beampos[1], rmin, rmax, 20)
    valid = np.logical_and(np.isfinite(pixel), np.isfinite(intensity))
    pixel = pixel[valid]
    intensity = intensity[valid]
    result = scipy.optimize.least_squares(
        powerlawtargetfunc,
        [1, -4],
        bounds=([0, -6], [np.inf, 0]),
        args=(pixel, intensity),
    )
    if not result.success:
        return np.nan
    return result.cost


def momentofinertia(beampos, matrix, mask, rmin, rmax):
    return -_momentofinertia(matrix, mask, beampos[0], beampos[1], rmin, rmax)


def azimuthal(beampos, matrix, mask, rmin, rmax):
    msk = maskforannulus(mask, beampos[0], beampos[1], rmin, rmax)
    phi, intensity, area = fastazimavg(matrix, msk, beampos[0], beampos[1], int((rmin + rmax) * np.pi / 2))
    return intensity[area > 0].std()


def azimuthal_fold(beampos, matrix, mask, rmin, rmax):
    msk = maskforannulus(mask, beampos[0], beampos[1], rmin, rmax)
    phi, intensity, area = fastazimavg(matrix, msk, beampos[0], beampos[1], int((rmin + rmax) * np.pi / 4) * 2)
    diff = intensity[:len(intensity) // 2] - intensity[len(intensity) // 2:]
    return diff[np.isfinite(diff)].mean()
