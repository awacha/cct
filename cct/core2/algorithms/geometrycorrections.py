import numpy as np


def solidangle(twotheta, dtwotheta, sd, dsd, pixelsize, dpixelsize):
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
    sac = sd ** 2 / np.cos(twotheta) ** 3 / pixelsize ** 2
    return (sac,
            sac * (4 * dsd ** 2 / sd ** 2 + 4 * dpixelsize ** 2 / pixelsize ** 2 + 9 * dtwotheta ** 2 * np.tan(
                twotheta) ** 2) ** 0.5)


def _angledependentabsorption_value(twotheta: np.ndarray, transmission: float):
    cor = np.ones_like(twotheta)
    if transmission == 1:
        return cor
    mud = -np.log(transmission)

    cor[twotheta > 0] = transmission * mud * (1 - 1 / np.cos(twotheta[twotheta > 0])) / (
            np.exp(-mud / np.cos(twotheta[twotheta > 0])) - transmission)
    return cor


def _angledependentabsorption_error(twotheta, dtwotheta, transmission, dtransmission):
    # calculated using sympy
    costth = np.cos(twotheta)
    sintth = np.sin(twotheta)
    lntrans = np.log(transmission)
    exp1 = np.exp(lntrans / costth)
    return ((transmission * costth - exp1 *
             lntrans * costth + exp1
             * lntrans - exp1 * costth) ** 2
            * (transmission ** 2 * dtwotheta ** 2 * lntrans ** 2 * sintth ** 2
               + dtransmission ** 2 * sintth ** 4 - 3 * dtransmission ** 2 * sintth ** 2
               - 2 * dtransmission ** 2 * costth ** 3 + 2 * dtransmission ** 2) /
            (transmission - exp1) ** 4) ** 0.5 * np.abs(costth) ** (-3.0)


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
    return (_angledependentabsorption_value(twotheta, transmission),
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
    costth = np.cos(twotheta)
    sintth = np.sin(twotheta)
    mu_air = mu0_air / 1000 * pressure
    dmu_air = dmu0_air / 1000 * pressure
    return (np.exp(mu_air * sampletodetectordistance / costth),
            np.sqrt(dmu_air ** 2 * sampletodetectordistance ** 2 *
                    np.exp(2 * mu_air * sampletodetectordistance / costth)
                    / costth ** 2 + dsampletodetectordistance ** 2 *
                    mu_air ** 2 * np.exp(2 * mu_air * sampletodetectordistance /
                                         costth) /
                    costth ** 2 + dtwotheta ** 2 * mu_air ** 2 *
                    sampletodetectordistance ** 2 *
                    np.exp(2 * mu_air * sampletodetectordistance / costth)
                    * sintth ** 2 / costth ** 4)
            )
