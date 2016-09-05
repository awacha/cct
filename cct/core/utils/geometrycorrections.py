import numpy as np

from sastool.misc.errorvalue import ErrorValue


def solidangle(twotheta, dtwotheta, sampletodetectordistance, dsampletodetectordistance, pixelsize):
    """Solid-angle correction for two-dimensional SAS images with error propagation

    Inputs:
        twotheta: matrix of two-theta values
        dtwotheta: matrix of absolute error of two-theta values
        sampletodetectordistance: sample-to-detector distance
        dsampletodetectordistance: absolute error of sample-to-detector distance

    Outputs two matrices of the same shape as twotheta. The scattering intensity
        matrix should be multiplied by the first one. The second one is the propagated
        error of the first one.
    """
    return ErrorValue(sampletodetectordistance ** 2 / np.cos(twotheta) ** 3,
                      (sampletodetectordistance * (4 * dsampletodetectordistance ** 2 * np.cos(twotheta) ** 2 +
                                                   9 * dtwotheta ** 2 * sampletodetectordistance ** 2 * np.sin(
                                                       twotheta) ** 2) ** 0.5
                       / np.cos(twotheta) ** 4)) / pixelsize ** 2


def _angledependentabsorption_value(twotheta, transmission):
    """Correction for angle-dependent absorption of the sample

    Inputs:
        twotheta: matrix of two-theta values
        transmission: the transmission of the sample (I_after/I_before, or
            exp(-mu*d))

    The output matrix is of the same shape as twotheta. The scattering intensity
        matrix should be multiplied by it. Note, that this does not corrects for
        sample transmission by itself, as the 2*theta -> 0 limit of this matrix
        is unity. Twotheta==0 and transmission==1 cases are handled correctly
        (the limit is 1 in both cases).
    """
    cor = np.ones(twotheta.shape)
    if transmission == 1:
        return cor
    mud = -np.log(transmission)

    cor[twotheta > 0] = transmission * mud * (1 - 1 / np.cos(twotheta[twotheta > 0])) / (
        np.exp(-mud / np.cos(twotheta[twotheta > 0])) - np.exp(-mud))
    return cor


def _angledependentabsorption_error_ugly(twotheta, dtwotheta, transmission, dtransmission):
    # calculated using sympy
    return ((transmission * np.cos(twotheta) - np.exp(np.log(transmission) / np.cos(twotheta)) *
             np.log(transmission) * np.cos(twotheta) + np.exp(np.log(transmission) / np.cos(twotheta))
             * np.log(transmission) - np.exp(np.log(transmission) / np.cos(twotheta)) * np.cos(twotheta)) ** 2
            * (transmission ** 2 * dtwotheta ** 2 * np.log(transmission) ** 2 * np.sin(twotheta) ** 2
               + dtransmission ** 2 * np.sin(twotheta) ** 4 - 3 * dtransmission ** 2 * np.sin(twotheta) ** 2
               - 2 * dtransmission ** 2 * np.cos(twotheta) ** 3 + 2 * dtransmission ** 2) /
            (transmission - np.exp(np.log(transmission) / np.cos(twotheta))) ** 4) ** 0.5 * \
           np.abs(np.cos(twotheta)) ** (-3.0)


def __create_adaerror_function():
    try:
        # noinspection PyUnresolvedReferences,PyPackageRequirements
        import sympy

        tth, dtth, T, dT = sympy.symbols('tth dtth T dT')
        mud = -sympy.log(T)
        corr = sympy.exp(-mud) * mud * (1 - 1 / sympy.cos(tth)) / (sympy.exp(-mud / sympy.cos(tth)) - sympy.exp(-mud))
        dcorr = (sympy.diff(corr, T) ** 2 * dT ** 2 + sympy.diff(corr, tth) ** 2 * dtth ** 2) ** 0.5
        func = sympy.lambdify((tth, dtth, T, dT), dcorr, "numpy")
        del sympy, tth, dtth, T, dT, mud, corr, dcorr
    except ImportError:
        func = _angledependentabsorption_error_ugly
    return func


_angledependentabsorption_error = __create_adaerror_function()


def angledependentabsorption(twotheta, dtwotheta, transmission, dtransmission):
    """Correction for angle-dependent absorption of the sample with error propagation

    Inputs:
        twotheta: matrix of two-theta values
        dtwotheta: matrix of absolute error of two-theta values
        transmission: the transmission of the sample (I_after/I_before, or
            exp(-mu*d))
        dtransmission: the absolute error of the transmission of the sample

    Two matrices are returned: the first one is the correction (intensity matrix
        should be multiplied by it), the second is its absolute error.
    """
    # error propagation formula calculated using sympy
    return ErrorValue(_angledependentabsorption_value(twotheta, transmission),
                      _angledependentabsorption_error(twotheta, dtwotheta, transmission, dtransmission))


def angledependentairtransmission(twotheta, dtwotheta,
                                  pressure, sampletodetectordistance,
                                  dsampletodetectordistance, mu0_air=1 / 883.49, dmu0_air=0):
    """Correction for the angle dependent absorption of air in the scattered
    beam path, with error propagation

    Inputs:
            twotheta: matrix of two-theta values
            dtwotheta: absolute error matrix of two-theta
            pressure: the air pressure in mbar
            sampletodetectordistance: sample-to-detector distance
            dsampletodetectordistance: error of the sample-to-detector distance
            mu0_air: the linear absorption coefficient of air at 1000 mbars, in 1/mm units.
                At 8 keV this is 1/883.49 1/mm
            dmu0_air: error of the linear absorption coefficient of air at 1000 mbars in 1/mm units

    1/mu_air and sampletodetectordistance should have the same dimension

    The scattering intensity matrix should be multiplied by the resulting
    correction matrix."""
    mu_air = mu0_air / 1000 * pressure
    dmu_air = dmu0_air / 1000 * pressure
    return ErrorValue(np.exp(mu_air * sampletodetectordistance / np.cos(twotheta)),
                      np.sqrt(dmu_air ** 2 * sampletodetectordistance ** 2 *
                              np.exp(2 * mu_air * sampletodetectordistance / np.cos(twotheta))
                              / np.cos(twotheta) ** 2 + dsampletodetectordistance ** 2 *
                              mu_air ** 2 * np.exp(2 * mu_air * sampletodetectordistance /
                                                   np.cos(twotheta)) /
                              np.cos(twotheta) ** 2 + dtwotheta ** 2 * mu_air ** 2 *
                              sampletodetectordistance ** 2 *
                              np.exp(2 * mu_air * sampletodetectordistance / np.cos(twotheta))
                              * np.sin(twotheta) ** 2 / np.cos(twotheta) ** 4)
                      )
