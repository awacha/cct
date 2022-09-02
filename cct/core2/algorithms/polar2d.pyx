# coding: utf-8
# cython: cdivision=True, wraparound=False, boundscheck=False, language_level=3, embedsignature=True
"""Polar representation of a scattering pattern"""
import numpy as np
cimport numpy as np
from cython.view cimport array as cvarray
np.import_array()
from libc.math cimport sqrt, sin, cos, M_PI, remainder, floor, NAN, tan, asin

def polar2D_q(double[:, :] image, double wavelength, double distance, double pixelsize, double center_row, double center_column, double[:] q, double[:] phi):
    """"""
    cdef:
        Py_ssize_t iq
        double lambdadiv4pi = wavelength/4/M_PI
        double distdivpixsize = distance / pixelsize
        Py_ssize_t Nq = q.size
        double[:] pixel = np.empty_like(q)

    for iq in range(Nq):
        pixel[iq] = distdivpixsize * tan(2*asin(q[iq]*lambdadiv4pi))
    return polar2D_pixel(image, center_row, center_column, pixel, phi)

def polar2D_pixel(double[:, :] image, double center_row, double center_column, double[:] pixel, double[:] phi):
    cdef:
        Py_ssize_t ipix, iphi, row, column
        Py_ssize_t Npix = pixel.size
        Py_ssize_t Nphi = phi.size
        double[:, :] polar = np.zeros((Nphi, Npix), np.double)
        double sinphi, cosphi

    for iphi in range(Nphi):
        sinphi = sin(phi[iphi])
        cosphi = cos(phi[iphi])
        for ipix in range(Npix):
            row = <Py_ssize_t>floor(center_row - pixel[ipix] * sinphi + 0.5)
            col = <Py_ssize_t>floor(center_column + pixel[ipix] * cosphi + 0.5)
            if (row < 0) or (col < 0) or (row >= image.shape[0]) or (col >= image.shape[1]):
                polar[iphi, ipix] = NAN
            else:
                polar[iphi, ipix] = image[row, col]
    return polar

