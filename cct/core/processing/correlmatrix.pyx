#cython: boundscheck=False, cdivision=True, embedsignature=True
import numpy as np
cimport numpy as np
from libc.math cimport log, nan, isfinite

np.import_array()

def correlmatrix_cython(np.ndarray[np.double_t, ndim=2] intensities not None, np.ndarray[np.double_t, ndim=2] errors not None, bint logarithmic=False):
    cdef Py_ssize_t Ncurves, Npoints, icurves, ipoints, jcurves, npoints
    cdef np.ndarray[np.double_t, ndim=2] cm
    cdef np.ndarray[np.uint8_t, ndim=2] valid
    cdef double cmpoint, weight, w
    cdef double NaN = nan('NaN')
    Ncurves=intensities.shape[1]
    Npoints=intensities.shape[0]
    if (errors.shape[1] != Ncurves) or (errors.shape[0] != Npoints):
        raise ValueError('Invalid shape of errors')
    valid = np.zeros((Npoints, Ncurves), dtype=np.uint8)
    cm = np.empty((Ncurves, Ncurves), dtype=np.double)
    for icurves in range(Ncurves):
        for ipoints in range(Npoints):
            valid[ipoints, icurves] = ((intensities[ipoints, icurves]>0) or (not logarithmic)) and (errors[ipoints, icurves]>0)
    for icurves in range(Ncurves):
        for jcurves in range(icurves+1, Ncurves):
            npoints=0
            cmpoint=0
            weight = 0
            for ipoints in range(Npoints):
                if not (valid[ipoints, icurves] and valid[ipoints, jcurves]):
                    continue
                if logarithmic:
                    w = (errors[ipoints, icurves]/intensities[ipoints,icurves])**2+ (errors[ipoints,jcurves]/intensities[ipoints,jcurves])**2
                    cmpoint+=(log(intensities[ipoints, icurves])-log(intensities[ipoints,jcurves]))**2/w
                else:
                    w = errors[ipoints, icurves]**2+errors[ipoints,jcurves]**2
                    cmpoint +=(intensities[ipoints,icurves]-intensities[ipoints,jcurves])**2/w
                weight+=1/w
                npoints+=1
            if npoints:
                cm[icurves,jcurves] = cm[jcurves, icurves] = cmpoint/weight
            else:
                print('Curve {} and {} have no common valid points!'.format(icurves,jcurves))
                cm[icurves, jcurves] = cm[jcurves,icurves] = NaN
    for icurves in range(Ncurves):
        cmpoint = 0
        npoints = 0
        for jcurves in range(Ncurves):
            if (jcurves != icurves) and isfinite(cm[icurves, jcurves]):
                cmpoint += cm[icurves, jcurves]
                npoints +=1
        if npoints>0:
            cm[icurves, icurves] = cmpoint / npoints
        else:
            cm[icurves, icurves] = NaN
    return cm
