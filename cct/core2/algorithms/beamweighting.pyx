# cython: cdivision=True, wraparound=False, boundscheck=False, language_level=3, embedsignature=True
from libc.math cimport sqrt, NAN
from libc.stdint cimport uint8_t

def beamweights(double [:,:] image not None, uint8_t [:,:] mask not None):
    """Calculate some statistics on an image

    :param image: the scattering image
    :type image: 2D array, double dtype
    :param mask: the mask: 0 is masked, nonzero is valid (not masked) pixel
    :type mask: 2D array, uint8 dtype
    :return: sum, max, center_row, center_col, sigma_row, sigma_col, pixelcount
    :rtype: tuple of (float, float, float, float, float, float, int)
    """
    cdef:
        Py_ssize_t irow, icol
        double meanrow=0, meanrow2=0, meancol=0, meancol2=0, sumimage=0, maximage=0
        Py_ssize_t pixelcount=0

    maximage=image[0,0]
    for irow in range(0, image.shape[0]):
        for icol in range(0, image.shape[1]):
            if image[irow, icol] <=0:
                continue
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
    if pixelcount == 0:
        return NAN, NAN, NAN, NAN, NAN, NAN, 0
    else:
        return sumimage, maximage, meanrow/sumimage, meancol/sumimage, sqrt((meanrow2 / sumimage - meanrow) / sumimage), sqrt((meancol2 / sumimage - meancol) / sumimage), pixelcount
