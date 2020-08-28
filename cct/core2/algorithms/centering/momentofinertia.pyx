# cython: cdivision=True, wraparound=False, boundscheck=False, language_level=3, embedsignature=True
from numpy cimport uint8_t
from libc.math cimport isfinite

def _momentofinertia(double [:, :] matrix, uint8_t [:,:] mask, double beamrow, double beamcol, double rmin, double rmax):
    cdef:
        Py_ssize_t irow, icol
        double moment= 0.0
        double radius2 = 0.0
        double rmin2 = rmin*rmin
        double rmax2 = rmax*rmax
    for irow in range(matrix.shape[0]):
        for icol in range(matrix.shape[1]):
            if mask[irow, icol] == 0:
                continue
            if not isfinite(matrix[irow, icol]):
                continue
            radius2 = (irow - beamrow)* (irow - beamrow) + (icol - beamcol) * (icol - beamcol)
            if (radius2 < rmin2) or (radius2 > rmax2):
                continue
            moment += radius2*matrix[irow, icol]
    return moment