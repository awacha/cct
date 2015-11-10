# pylint: disable-msg-cat=WCREFI
# cython: boundscheck=False
# cython: embedsignature=True
# cython: cdivision=True
import numpy as np

cimport numpy as np
from libc.stdlib cimport *
from libc.math cimport *

# cdef extern from "math.h":
#    int isfinite(double)
#    double INFINITY
#    double floor(double)
#    double ceil(double)
#    double fmod(double,double)
#    double fabs(double)

cdef enum AbscissaKind:
    PIXEL = 0
    DETRADIUS = 1
    TWOTHETA = 2
    Q = 3

cdef enum ErrorPropagation:
    INDEPENDENT_SAME = 0
    AVERAGE = 1
    GAUSS = 2
    MIXED = 3


def autoabscissa(double wavelength, double distance, double pixelsize,
                 double bcx, double bcy,
                 np.ndarray[np.uint8_t, ndim = 2] mask not None,
                 bint linspacing = True, int abscissa_kind = 0):
    """Determine q-scale automatically

    Inputs:
        wavelength: wavelength in nanometers
        distance: sample-detector distance in mm
        pixelsize: pixel size in mm
        bcx, bcy: beam position (starting from 0)
        mask: mask matrix (True means valid, False is masked).
        linspacing: if linear spacing is expected. Otherwise log10 spacing.
        abscissa_kind: an integer number determining the abscissa values of
            the result. Can be:
            3: q (4*pi*sin(theta)/lambda)
            2: 2*theta
            1: detector radius in length units (mm, if the pixel size is in mm)
            0: pixels

    Output: the q scale in a numpy vector. If either wavelength or distance or xres
        or yres is nonpositive, pixel vector is returned, which is guaranteed to
        be spaced by 1 pixels.
    """
    # determine the q-scale to be used automatically.
    cdef double qmin, qmax
    cdef Py_ssize_t ix, iy, M, N
    cdef bint flagq

    M = mask.shape[0];
    N = mask.shape[1];
    qmin = 1e20;
    qmax = -10
    for ix from 0 <= ix < M:
        for iy from 0 <= iy < N:
            if not mask[ix, iy]:
                continue
            x = ((ix - bcx) * pixelsize)
            y = ((iy - bcy) * pixelsize)
            if abscissa_kind == Q:
                q1 = 4 * M_PI * sin(0.5 * atan(sqrt(x * x + y * y) / distance)) / wavelength
            elif abscissa_kind == TWOTHETA:
                q1 = atan(sqrt(x * x + y * y) / distance)
            elif abscissa_kind == DETRADIUS:
                q1 = (sqrt(x * x + y * y))
            elif abscissa_kind == PIXEL:
                q1 = (sqrt((ix - bcx) * (ix - bcx) + (iy - bcy) * (iy - bcy)))
            if (q1 > qmax):
                qmax = q1
            if (q1 < qmin):
                qmin = q1
    if linspacing:
        return np.linspace(qmin, qmax, sqrt(M * M + N * N) / 2)
    else:
        return np.logspace(np.log10(qmin), np.log10(qmax), sqrt(M * M + N * N) / 2)


def radint_fullq(np.ndarray[np.double_t, ndim = 2] data not None,
                 np.ndarray[np.double_t, ndim = 2] dataerr,
                 double wavelength, double wavelengtherr, double distance,
                 double distanceerr, double pixelsize, double bcx,
                 double bcxerr, double bcy, double bcyerr,
                 np.ndarray[np.uint8_t, ndim = 2] mask,
                 np.ndarray[np.double_t, ndim = 1] q = None,
                 int errorpropagation = 2, int abscissa_errorpropagation = 2,
                 bint autoqrange_linear = True, int abscissa_kind = 3):
    """ Radial averaging of scattering images, full azimuthal range

    Inputs:
        data: the intensity matrix
        dataerr: the error (standard deviation) matrix (of the same size as
            'data'). Or None to disregard it.
        wavelength: the real photon/neutron wavelength (units of this
            determine the units of q at the end).
        wavelengtherror: absolute error of the wavelength.
        distance: the distance from the sample to the detector.
        distanceerror: absolute error of the distance from the sample to the
            detector.
        pixelsize: the pixel size. Units are the same as the sample-to-detector
            distance.
        bcx: the coordinate of the beam center along the first axis (row
            coordinates), starting from 0
        bcxerr: error of the X beam center coordinate
        bcy: the coordinate of the beam center along the second axis (column
            coordiantes), starting from 0
        bcyerr: error of the Y beam center coordinate
        mask: the mask matrix (of the same size as 'data'). Nonzero is masked,
            zero is not masked. None to omit.
        q: the q (or pixel) points at which the integration is requested, in
            1/Angstroem (or pixel) units. If None, optimum range will be chosen
            automagically by taking the mask and the geometry into account.
        errorpropagation: an integer number determining the type of error
            propagation. Can be:
            0: intensities falling to the same q-bin are assumed to be independent
                measurements of the same quantity, thus they will be weighted by
                the inverse squared of the error bars, and the error will be the
                inverse of the sum of these inverses.
            1: error bars are simply averaged, then divided by sqrt(# of pixels
                belonging to the bin).
            2: squared error propagation of independent quantities
        abscissa_errorpropagation: an integer number determining the type of
            error propagation, similar to `errorpropagation`.
        autoqrange_linear: if the automatically determined q-range is to be
            linspace-d. Otherwise log10 spacing will be applied.
        abscissa_kind: an integer number determining the abscissa values of
            the result. Can be:
            3: q (4*pi*sin(theta)/lambda)
            2: 2*theta
            1: detector radius in length units (mm, if the pixel size is in mm)
            0: pixels

    X is the first index (row number), Y is the second index (column number).
    Counting starts from zero.

    Outputs: q, qerror, Intensity, Error, Area
    """
    cdef np.ndarray[np.double_t, ndim = 1] qout, dqout, Intensity, Error, Area, pixelout
    cdef np.ndarray[np.double_t, ndim = 2] x, y
    cdef Py_ssize_t ix, iy, l, maxlog, M, N, Numq, count_invalid_error=0, count_invalid_data=0, count_masked=0, count_underflow=0, count_overflow=0
    cdef double q1, dq1, rho
    cdef double * qmax
    cdef double * Intensity_squared
    cdef double * q2

    # Process input data
    # array shapes
    if dataerr is None:
        dataerr = np.ones_like(data, dtype=np.double)
    if mask is None:
        mask = np.ones_like(data, dtype=np.bool)
    assert(data.shape[0] == dataerr.shape[0])
    assert(data.shape[1] == dataerr.shape[1])
    assert(data.shape[0] == mask.shape[0])
    assert(data.shape[1] == mask.shape[1])
    M = data.shape[0]
    N = data.shape[1]
    # if the q-scale was not supplied, create one.
    if q is None:
        q = autoabscissa(wavelength, distance, pixelsize, bcx, bcy, mask, autoqrange_linear, abscissa_kind);
    Numq = len(q)
    # initialize the output vectors
    Intensity = np.zeros(Numq, dtype=np.double)
    Error = np.zeros(Numq, dtype=np.double)
    Area = np.zeros(Numq, dtype=np.double)
    qout = np.zeros(Numq, dtype=np.double)
    dqout = np.zeros(Numq, dtype=np.double)
    pixelout = np.zeros(Numq, dtype=np.double)
    # set the upper bounds of the q-bins in qmax
    qmax = < double * > malloc(Numq * sizeof(double))
    Intensity_squared = < double * > malloc(Numq * sizeof(double))
    q2 = < double * > malloc(Numq * sizeof(double))
    for l from 0 <= l < Numq:
        # initialize the weight and the qmax array.
        if l == Numq - 1:
            qmax[l] = q[Numq - 1]
        else:
            qmax[l] = 0.5 * (q[l] + q[l + 1])
        Intensity_squared[l] = q2[l] = 0
    x = np.arange(M)[:, np.newaxis] - bcx
    y = np.arange(N)[np.newaxis, :] - bcy
    xerr = np.sqrt(bcxerr * bcxerr + 0.25)
    yerr = np.sqrt(bcyerr * bcyerr + 0.25)
    r = np.sqrt(x * x + y * y)
    dr = np.sqrt(x * x * xerr * xerr + y * y * yerr * yerr) / r
    if abscissa_kind >= DETRADIUS:
        r *= pixelsize
        dr *= pixelsize
    if abscissa_kind >= TWOTHETA:
        dr = np.sqrt(
            dr * dr / distance / distance + r * r / distance / distance / distance / distance * distanceerr * distanceerr)
        r /= distance
        dr = (1 / (1 + r * r)) * dr
        r = np.arctan(r)
    if abscissa_kind >= Q:
        dr = 2 * np.pi * np.abs(np.cos(0.5 * r)) * dr
        r = np.sin(0.5 * r) * 4 * np.pi
        dr = np.sqrt(
            dr * dr / wavelength / wavelength + r * r / wavelength / wavelength / wavelength / wavelength * wavelengtherr * wavelengtherr)
        r /= wavelength
    # loop through pixels
    for ix from 0 <= ix < M:  # rows
        for iy from 0 <= iy < N:  # columns
            if not mask[ix, iy]:
                # if the pixel is masked, disregard it.
                count_masked+=1
                continue
            if not isfinite(data[ix, iy]):
                # disregard nonfinite (NaN or inf) pixels.
                count_invalid_data+=1
                continue
            if not isfinite(dataerr[ix, iy]):
                # disregard nonfinite (NaN or inf) pixels.
                count_invalid_error+=1
                continue
            dataerr_current = dataerr[ix, iy]
            if errorpropagation == 0 and dataerr[ix, iy] <= 0:
                dataerr_current = 1
            if r[ix, iy] < q[0]:  # q underflow
                count_underflow+=1
                continue
            if r[ix, iy] > q[Numq - 1]:  # q overflow
                count_overflow+=1
                continue
            for l from 0 <= l < Numq:  # Find the q-bin
                if (r[ix, iy] > qmax[l]):
                    # not there yet
                    continue
                # we reach this point only if q1 is in the l-th bin. Calculate
                # the contributions of this pixel to the weighted average.
                if errorpropagation == MIXED:
                    Error[l] += dataerr_current * dataerr_current
                    Intensity[l] += data[ix, iy]
                    Intensity_squared[l] += data[ix, iy] * data[ix, iy]
                elif errorpropagation == GAUSS:
                    Error[l] += dataerr_current * dataerr_current
                    Intensity[l] += data[ix, iy]
                elif errorpropagation == AVERAGE:
                    Error[l] += dataerr_current
                    Intensity[l] += data[ix, iy]
                elif errorpropagation == INDEPENDENT_SAME:
                    Error[l] += 1 / (dataerr_current * dataerr_current)
                    Intensity[l] += data[ix, iy] / (dataerr_current * dataerr_current)
                else:
                    raise NotImplementedError(errorpropagation)
                if abscissa_errorpropagation == MIXED:
                    dqout[l] += dr[ix, iy] * dr[ix, iy]
                    qout[l] += r[ix, iy]
                    q2[l] += r[ix, iy] * r[ix, iy]
                elif abscissa_errorpropagation == GAUSS:
                    dqout[l] += dr[ix, iy] * dr[ix, iy]
                    qout[l] += r[ix, iy]
                elif abscissa_errorpropagation == AVERAGE:
                    dqout[l] += dr[ix, iy]
                    qout[l] += r[ix, iy]
                elif abscissa_errorpropagation == INDEPENDENT_SAME:
                    dqout[l] += 1 / (dr[ix, iy] * dr[ix, iy])
                    qout[l] += r[ix, iy] / (dr[ix, iy] * dr[ix, iy])
                else:
                    raise NotImplementedError(abscissa_errorpropagation)
                Area[l] += 1
                break  # avoid counting this pixel into higher q-bins.
            # normalize the results
    #print('Radial averaging statistics.\n  Masked: %d\n  Invalid data: %d\n  Invalid error: %d\n  Underflow: %d\n  Overflow: %d'%(
    #    count_masked, count_invalid_data, count_invalid_error, count_underflow, count_overflow))
    for l from 0 <= l < Numq:
        if Area[l] == 0:
            continue
        if abscissa_errorpropagation == MIXED:
            if Area[l] > 1:
                rho = sqrt((q2[l] - qout[l] * qout[l] / Area[l]) / (Area[l] - 1)) / sqrt(Area[l])
            else:
                rho = 0
            r = sqrt(dqout[l]) / Area[l]
            if rho > r:
                dqout[l] = rho
            else:
                dqout[l] = r
            qout[l] /= Area[l]
        elif abscissa_errorpropagation == GAUSS:
            qout[l] /= Area[l]
            dqout[l] = sqrt(dqout[l]) / Area[l]
        elif abscissa_errorpropagation == AVERAGE:
            qout[l] /= Area[l]
            dqout[l] = dqout[l] / Area[l]
        elif abscissa_errorpropagation == INDEPENDENT_SAME:
            qout[l] /= dqout[l]
            dqout[l] = sqrt(1 / dqout[l])
        else:
            raise NotImplementedError

        if Error[l] == 0:
            pass
        elif errorpropagation == MIXED:
            # we have two kinds of error: one from counting statistics, i.e. the empirical standard deviation
            # of the intensities, and one from the squared error propagation. Take the larger.

            # we re-use variables, rho will be the error from the counting statistics, r the one from error
            # propagation.
            if Area[l] > 1:
                rho = sqrt((Intensity_squared[l] - Intensity[l] * Intensity[l] / Area[l]) / (Area[l] - 1)) / sqrt(Area[l])
            else:
                rho = 0
            r = sqrt(Error[l]) / Area[l]
            if rho > r:
                Error[l] = rho
            else:
                Error[l] = r
        elif errorpropagation == GAUSS:
            Error[l] = sqrt(Error[l]) / Area[l]
        elif errorpropagation == AVERAGE:
            Error[l] = Error[l] / Area[l] ** 2
        elif errorpropagation == INDEPENDENT_SAME:
            Intensity[l] /= Error[l]
            Error[l] = sqrt(1 / Error[l])
        if errorpropagation != INDEPENDENT_SAME:
            Intensity[l] /= Area[l]

        # cleanup memory
    free(qmax)
    free(Intensity_squared)
    free(q2)
    return qout, dqout, Intensity, Error, Area
