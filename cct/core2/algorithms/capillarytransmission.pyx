# cython: language_level=3, boundscheck=False, wraparound=False, initializedcheck=False, nonecheck=False, overflowcheck=False, embedsignature=True, cdivision=True
# distutils: define_macros=NPY_NO_DEPRECATED_API=NPY_1_7_API_VERSION
cimport numpy as np
import numpy as np
from cpython.mem cimport PyMem_Free, PyMem_Malloc
from libc.math cimport exp, fabs, sqrt
from libc.stdlib cimport malloc, free

def capillarytransmission(
    const double[:] position,
    const double center,
    const double outer_diameter,
    const double wall_thickness,
    const double mu_sample,
    const double mu_wall,
    const double beam_sigma,
    const Py_ssize_t Nbeam):
    """Calculate the transmission scan curve of a capillary

    :param position: the x coordinates of the scan
    :type position: np.ndarray of dtype=double
    :param center: the coordinate of the capillary center
    :type center: double (float)
    :param outer_diameter: the outer diameter of the capillary
    :type outer_diameter: double (float)
    :param wall_thickness: the wall thickness of the capillary
    :type wall_thickness: double (float)
    :param mu_sample: the linear absorption coefficient of the sample
    :type mu_sample: double (float)
    :param mu_wall: the linear absorption coefficient of the wall
    :type mu_wall: double (float)
    :param beam_sigma: the std.dev parameter of the Gaussian beam profile
    :type beam_sigma: double (float)
    :param Nbeam: number of points for discrete integration
    :type Nbeam: Py_ssize_t (int)
    :return: the transmitted beam intensity, measured at each point in `position`
    :rtype: np.ndarray of dtype=double, same shape as `position`
    """

    cdef:
        np.ndarray[np.double_t, ndim=1] transmission = np.empty_like(position)
        Py_ssize_t ipos, ibeam
        double R = outer_diameter * 0.5
        double r, t, d_wall, d_sample
        double *beamprofile = <double *>PyMem_Malloc(sizeof(double)*Nbeam)
        double beamsum = 0
        double dbeam = 6*beam_sigma/(Nbeam-1)

    for ibeam in range(Nbeam):
        r = -3 * beam_sigma + dbeam*ibeam
        beamprofile[ibeam] = exp(-r*r/(2*beam_sigma*beam_sigma))
        beamsum += beamprofile[ibeam]
    for ibeam in range(Nbeam):
        beamprofile[ibeam] /= beamsum

    for ipos in range(position.size):
        t = 0
        for ibeam in range(Nbeam):
            r = fabs(position[ipos] - 3*beam_sigma + dbeam*ibeam - center)
            if r > R:
                d_wall = 0
                d_sample = 0
            elif r > (R - wall_thickness):
                d_wall = 2*sqrt(R**2-r**2)
                d_sample = 0
            else:
                d_sample = 2* sqrt((R-wall_thickness)**2-r**2)
                d_wall = 2* sqrt(R**2-r**2) - d_sample
            t += exp(- mu_wall * d_wall)*exp(-mu_sample*d_sample) * beamprofile[ibeam]
        transmission[ipos] = t
    PyMem_Free(beamprofile)
    return transmission
