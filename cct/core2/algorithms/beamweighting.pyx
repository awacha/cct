# cython: cdivision=True, wraparound=False, boundscheck=False, language_level=3, embedsignature=True
from libc.math cimport sqrt
from libc.stdint cimport uint8_t

def beamweights(double [:,:] image not None, uint8_t [:,:] mask not None):
    cdef:
        Py_ssize_t irow, icol
        double meanrow=0, meanrow2=0, meancol=0, meancol2=0, sumimage=0, maximage=0
        Py_ssize_t pixelcount=0

    maximage=image[0,0]
    for irow in range(0, image.shape[0]):
        for icol in range(0, image.shape[1]):
            if mask[irow, icol] == 0:
                continue
            if image[irow,icol] > maximage:
                maximage = image[irow, icol]
            sumimage += image[irow, icol]
            meanrow += irow * image[irow, icol]
            meanrow2 += irow * irow * image[irow, icol]
            meancol += icol * image[irow, icol]
            meancol2 += icol * icol* image[irow, icol]
            pixelcount += 1
    return sumimage, maximage, meanrow/sumimage, meancol/sumimage, sqrt((meanrow2 / sumimage - meanrow) / sumimage), sqrt((meancol2 / sumimage - meancol) / sumimage), pixelcount
