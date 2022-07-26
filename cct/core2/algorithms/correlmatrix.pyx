#cython: boundscheck=False, cdivision=True, embedsignature=True, language_level=3, initializedcheck=False
import numpy as np
cimport numpy as np
from cython.parallel import prange
from libc.math cimport log, nan, isfinite
np.import_array()

def correlmatrix_cython(double[:,:] intensities not None, double[:,:] errors not None, bint logarithmic=False):
    """Calculate the correlation matrix of scattering curves

    The c_ij element of the symmetric correlation matrix is calculated as:

    c_ij = sum_k( 1/(E_i(q_k)**2 + E_j(q_k)**2) * (I_i(q_k)-I_j(q_k))**2) / sum_k (1/(E_i(q_k)**2+E_j(q_k)**2))

    where I_i(q_k) and E_i(q_k) is the intensity and the absolute error, respectively, of the i-th measurement
    at the k-th q point.

    With the above method, c_ii would be zero. c_ii is set therefore to:

    c_ii = < c_ij >_{j!=i}

    If logarithmic calculation is required, the following replacements are done:

    I -> ln(I)
    E -> E/I

    In this case, nonpositive intensities are automatically skipped.

    :param intensities: an array containing the intensities of independent measurements in columns
    :type intensities: MxN np.ndarray, double dtype
    :param errors: an array containing the absolute errors of independent measurements in columns
    :type errors: MxN np.ndarray, double dtype
    :param logarithmic: if logarithmic distances are to be used
    :type logarithmic: bool
    :return: the correlation matrix
    :rtype: NxN np.ndarray, double dtype
    """
    cdef Py_ssize_t Ncurves, Npoints, icurves, ipoints, jcurves, npoints
    cdef double[:,:] cm
    cdef double weight
    cdef double cmpoint, w
    cdef unsigned char[:,:] mymask
    cdef double NaN = nan('NaN')
    Ncurves=intensities.shape[1]
    Npoints=intensities.shape[0]
    if (errors.shape[1] != Ncurves) or (errors.shape[0] != Npoints):
        raise ValueError('Invalid shape of errors')
    mymask = np.empty((Npoints, Ncurves), np.uint8)
    cm = np.empty((Ncurves, Ncurves), np.double)
    for icurves in range(Ncurves):
        for ipoints in range(Npoints):
            mymask[ipoints, icurves] = (((intensities[ipoints, icurves])>0) or (not logarithmic)) and (errors[ipoints, icurves]>0)
    for icurves in prange(Ncurves, nogil=True, schedule='guided'):
        for jcurves in range(icurves+1, Ncurves):
            cmpoint=0
            weight = 0
            for ipoints in range(Npoints):
                if (not mymask[ipoints, icurves]) or (not mymask[ipoints, jcurves]):
                    continue
                if logarithmic:
                    w = (errors[ipoints, icurves]/intensities[ipoints,icurves])**2+ (errors[ipoints,jcurves]/intensities[ipoints,jcurves])**2
                    cmpoint=cmpoint+(log(intensities[ipoints, icurves])-log(intensities[ipoints,jcurves]))**2/w
                else:
                    w = errors[ipoints, icurves]**2+errors[ipoints,jcurves]**2
                    cmpoint=cmpoint +(intensities[ipoints,icurves]-intensities[ipoints,jcurves])**2/w
                weight=weight+1/w
            if weight>0:
                cm[icurves,jcurves]=cm[jcurves,icurves]=cmpoint/weight
            else:
                cm[icurves, jcurves]=cm[jcurves,icurves]=NaN
    for icurves in range(Ncurves):
        cmpoint = 0
        npoints = 0
        for jcurves in range(Ncurves):
            if (jcurves != icurves) and isfinite(cm[icurves,jcurves]):
                cmpoint = cmpoint + cm[icurves,jcurves]
                npoints = npoints+1
        if npoints>0:
            cm[icurves,icurves] = cmpoint / npoints
        else:
            cm[icurves, icurves] = NaN
    del mymask
    return cm


def correlmatrix2d_cython(double[:,:,:] intensities not None,
                          double[:,:,:] errors not None,
                          unsigned char [:,:] mask not None):
    """Calculate the correlation matrix of scattering patterns

    The c_ij element of the symmetric correlation matrix is calculated as:

    c_ij = sum_{k,l}( 1/(E_i(q_{k,l})**2 + E_j(q_{k,l})**2) * (I_i(q_{k,l})-I_j(q_{k,l}))**2) / sum_{k,l} (1/(E_i(q_{k,l})**2+E_j(q_{k,l})**2))

    where I_i(q_{k,l}) and E_i(q_{k,l}) is the intensity and the absolute error, respectively, of the i-th measurement
    at the {k,l} pixel.

    With the above method, c_ii would be zero. c_ii is set therefore to:

    c_ii = < c_ij >_{j!=i}

    :param intensities: an array containing the intensities of independent measurements in columns
    :type intensities: MxN np.ndarray, double dtype
    :param errors: an array containing the absolute errors of independent measurements in columns
    :type errors: MxN np.ndarray, double dtype
    :param mask: mask matrix. Pixels where the mask is zero will be disregarded.
    :type mask: MxN np.ndarray, uint8 dtype
    :return: the correlation matrix
    :rtype: NxN np.ndarray, double dtype
    """

    cdef Py_ssize_t Ncurves, Nrows, Ncolumns, icurve, irow, icolumn, jcurve, npoints
    cdef double[:,:] cmout #= np.empty((intensities.shape[2], intensities.shape[2]), np.double) # output correlation matrix
    cdef double weight  # weights
    cdef double cmpoint, w
    cdef double NaN = nan('NaN')
    cdef unsigned char[:,:] mymask = np.empty((intensities.shape[0], intensities.shape[1]), np.uint8)

    Ncurves=intensities.shape[2]
    Ncolumns=intensities.shape[1]
    Nrows=intensities.shape[0]

    if (errors.shape[2] != Ncurves) or (errors.shape[0] != Nrows) or (errors.shape[1] != Ncolumns):
        raise ValueError('Invalid shape of errors')

    for irow in range(Nrows):
        for icolumn in range(Ncolumns):
            mymask[irow, icolumn] = mask[irow, icolumn]
            if mymask[irow, icolumn] == 0:
                continue
            for icurve in range(Ncurves):
                if not isfinite(intensities[irow, icolumn, icurve]) or not isfinite(errors[irow, icolumn, icurve]):
                    mymask[irow, icolumn] = 0
                    break
    cmout = np.empty((Ncurves, Ncurves), np.double)
    for icurve in prange(Ncurves, nogil=True, schedule='guided'):
        for jcurve in range(icurve+1, Ncurves):
            # calculate the icurve,jcurve element of the correlation matrix
            cmpoint=0
            weight=0
            for irow in range(Nrows):
                for icolumn in range(Ncolumns):
                    if mymask[irow, icolumn]==0:
                        continue
#                    if logarithmic:
#                        w = (errors[ipoints, icurves]/intensities[ipoints,icurves])**2+ (errors[ipoints,jcurves]/intensities[ipoints,jcurves])**2
#                        cm[icurves + jcurves*Ncurves]+=(log(intensities[ipoints, icurves])-log(intensities[ipoints,jcurves]))**2/w
#                    else:
                    w = errors[irow, icolumn, icurve]**2+errors[irow, icolumn, jcurve]**2
                    cmpoint+=(intensities[irow, icolumn,icurve]-intensities[irow, icolumn, jcurve])**2/w
                    weight=weight+1/w
            if weight>0:
                cmpoint=cmpoint/weight
            else:
                cmpoint=NaN
            cmout[icurve, jcurve]=cmout[jcurve,icurve]=cmpoint
    for icurve in range(Ncurves):
        cmpoint = 0
        npoints = 0
        for jcurve in range(Ncurves):
            if (jcurve != icurve) and isfinite(cmout[icurve, jcurve]):
                cmpoint += cmout[icurve, jcurve]
                npoints +=1
        if npoints>0:
            cmout[icurve, icurve] = cmpoint / npoints
        else:
            cmout[icurve, icurve] = NaN
    return cmout
