import logging
from typing import Tuple

import numpy as np
import scipy.optimize

from .targetfunctions import peakheight, peakwidth, slices, azimuthal, azimuthal_fold, momentofinertia

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

centeringalgorithms = {
    'Peak height': peakheight,
    'Peak width': peakwidth,
    'Opposing slices': slices,
    'Flat azimuthal': azimuthal,
    'Pi-periodic azimuthal': azimuthal_fold,
    'Moment of inertia': momentofinertia, }


def findbeam_crude(targetfunc, exposure, rmin, rmax, d=30, N=10) -> Tuple[float, float]:
    bestvalue = np.inf
    bestposition = None
    for irow, beamrow in enumerate(
            np.linspace(exposure.header.beamposrow[0] - d, exposure.header.beamposrow[0] + d, N)):
        for icol, beamcol in enumerate(
                np.linspace(exposure.header.beamposcol[0] - d, exposure.header.beamposcol[0] + d, N)):
            value = targetfunc((beamrow, beamcol), exposure.intensity, exposure.mask, rmin, rmax)
            if value < bestvalue:
                bestvalue = value
                bestposition = (beamrow, beamcol)
    return bestposition


def findbeam(algorithm, exposure, rmin, rmax, dcrude=30, Ncrude=10):
    if dcrude > 0 and Ncrude > 2:
        crudeposition = findbeam_crude(algorithm, exposure, rmin, rmax, dcrude, Ncrude)
    else:
        crudeposition = exposure.header.beamposrow[0], exposure.header.beamposcol[0]
    result = scipy.optimize.minimize(
        algorithm,
        np.array(crudeposition),
        args=(exposure.intensity, exposure.mask, rmin, rmax),
        method='L-BFGS-B',
        options={'ftol': 1e7 * np.finfo(float).eps},
    )
    ftol = 1e7 * np.finfo(float).eps  # L-BFGS-B default factr value is 1e7
    covar = max(1, np.abs(result.fun)) * ftol * result.hess_inv.todense()
    return (result.x[0], covar[0, 0] ** 0.5), (result.x[1], covar[1, 1] ** 0.5)
