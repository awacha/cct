import numpy as np
from sastool.misc.easylsq import nonlinear_leastsquares, nonlinear_odr

from .errorvalue import ErrorValue


class SASCurve(object):
    def __init__(self, x, y, dx, dy, legend=None):
        self._x = ErrorValue(x, dx)
        self._y = ErrorValue(y, dy)
        self._legend = legend

    def trim(self, xmin=-np.inf, xmax=np.inf):
        idx = (self._x.val >= xmin) & (self._x.val <= xmax)
        return SASCurve(self._x.val[idx], self._y.val[idx], self._x.err[idx],
                        self._y.err[idx], self._legend)

    def fit(self, fitfunction, initial_parameters):
        ret = nonlinear_leastsquares(self._x.val, self._y.val, self._y.err,
                                     fitfunction, initial_parameters)
        fitted = SASCurve(self._x.val, ret['func_eval'], None, None,
                          'fit to ' + self._legend)
        return ret + (fitted, )

    def odr(self, fitfunction, initial_parameters):
        ret = nonlinear_odr(self._x.val, self._y.val, self._x.err, self._y.err,
                            fitfunction, initial_parameters)
        fitted = SASCurve(self._x.val, ret['func_eval'], None, None,
                          'fit to ' + self._legend)
        return ret + (fitted, )

    @property
    def q(self):
        return self._x.val

    @property
    def dq(self):
        return self._x.err

    @property
    def intensity(self):
        return self._y.val

    @property
    def error(self):
        return self._y.err
