# cython: cdivision=True, wraparound=False, boundscheck=False, language_level=3, embedsignature=True
from libc.math cimport sqrt

def beamweights(double [:,:] image):
    cdef:
        Py_ssize_t irow, icol
        double meanrow=0, meanrow2=0, meancol=0, meancol2=0, sumimage=0, maximage=0

    maximage=image[0,0]
    for irow in range(0, image.shape[0]):
        for icol in range(0, image.shape[1]):
            if image[irow,icol] > maximage:
                maximage = image[irow, icol]
            sumimage += image[irow, icol]
            meanrow += irow * image[irow, icol]
            meanrow2 += irow * irow * image[irow, icol]
            meancol += icol * image[irow, icol]
            meancol2 += icol * icol* image[irow, icol]
    return sumimage, maximage, meanrow/sumimage, meancol/sumimage, sqrt((meanrow2 / sumimage - meanrow) / sumimage), sqrt((meancol2 / sumimage - meancol) / sumimage)
