#cython: boundscheck=False, cdivision=True, embedsignature=True
import numpy as np
cimport numpy as np
from libc.math cimport log, nan, isfinite
from cython.parallel import prange, parallel
from cpython.mem cimport PyMem_Malloc, PyMem_Free

np.import_array()

def correlmatrix_cython(double[:,:] intensities not None, double[:,:] errors not None, bint logarithmic=False):
    cdef Py_ssize_t Ncurves, Npoints, icurves, ipoints, jcurves, npoints
    cdef np.ndarray[np.double_t, ndim=2] cmout
    cdef double *cm
    cdef double *weight
    cdef int *valid
    cdef double cmpoint, w
    cdef double NaN = nan('NaN')
    Ncurves=intensities.shape[1]
    Npoints=intensities.shape[0]
    if (errors.shape[1] != Ncurves) or (errors.shape[0] != Npoints):
        raise ValueError('Invalid shape of errors')
    valid = <int*>PyMem_Malloc(sizeof(int)*Ncurves*Npoints)
    cm = <double*>PyMem_Malloc(sizeof(double)*Ncurves*Ncurves)
    weight = <double*>PyMem_Malloc(sizeof(double)*Ncurves*Ncurves)
    cmout = np.empty((Ncurves, Ncurves), np.double)
    for icurves in range(Ncurves):
        for ipoints in range(Npoints):
            valid[ipoints+icurves*Npoints] = ((intensities[ipoints, icurves]>0) or (not logarithmic)) and (errors[ipoints, icurves]>0)
    for icurves in prange(Ncurves, nogil=True, schedule='guided'):
#    for icurves in range(Ncurves):
        for jcurves in range(icurves+1, Ncurves):
            cm[icurves + jcurves*Ncurves] = cm[jcurves + icurves*Ncurves] = 0
            weight[icurves + jcurves*Ncurves] = 0
            for ipoints in range(Npoints):
                if not (valid[ipoints + icurves*Npoints] and valid[ipoints + jcurves*Npoints]):
                    continue
                if logarithmic:
                    w = (errors[ipoints, icurves]/intensities[ipoints,icurves])**2+ (errors[ipoints,jcurves]/intensities[ipoints,jcurves])**2
                    cm[icurves + jcurves*Ncurves]+=(log(intensities[ipoints, icurves])-log(intensities[ipoints,jcurves]))**2/w
                else:
                    w = errors[ipoints, icurves]**2+errors[ipoints,jcurves]**2
                    cm[icurves + jcurves*Ncurves] +=(intensities[ipoints,icurves]-intensities[ipoints,jcurves])**2/w
                weight[icurves + jcurves*Ncurves]+=1/w
    for icurves in range(Ncurves):
        for jcurves in range(icurves+1,Ncurves):
            if weight[icurves + jcurves*Ncurves] > 0:
                cm[icurves + jcurves*Ncurves] = cm[jcurves + icurves*Ncurves] = cm[icurves + jcurves*Ncurves]/weight[icurves + jcurves*Ncurves]
            else:
                cm[icurves + jcurves*Ncurves] = cm[jcurves + icurves*Ncurves] = NaN
    for icurves in range(Ncurves):
        cmpoint = 0
        npoints = 0
        for jcurves in range(Ncurves):
            if (jcurves != icurves) and isfinite(cm[icurves + jcurves*Ncurves]):
                cmpoint += cm[icurves + jcurves*Ncurves]
                npoints +=1
        if npoints>0:
            cm[icurves + icurves*Ncurves] = cmpoint / npoints
        else:
            cm[icurves + icurves*Ncurves] = NaN
    for icurves in range(Ncurves):
        for jcurves in range(Ncurves):
            cmout[icurves, jcurves] = cm[icurves + jcurves*Ncurves]
    PyMem_Free(valid)
    PyMem_Free(weight)
    PyMem_Free(cm)
    return cmout
