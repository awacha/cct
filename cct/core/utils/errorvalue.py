import copy
import logging
import math
import numbers
import re

import numpy as np

from .arithmetic import ArithmeticBase

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

__all__ = ['ErrorValue']


class ErrorValue(ArithmeticBase):
    """Class to hold a value and its uncertainty (1sigma, absolute error etc.).

    Main features:
        o Easy access to the value and its uncertainty through the `.val` and
            `.err` fields.
        o Basic arithmetic operations (+, -, *, /, **) are supported.
        o Can be instantiated easily by ``ErrorValue(value, [error])`` from:
            - scalar numbers
            - numpy ndarrays
            - other instances of `ErrorValue` (aka. "copy constructor")
            - homogeneous Python sequences of `ErrorValue` instances or scalar
                numbers
        o Intuitive string representation; the number of decimals is determined
            by the magnitude of the uncertainty (see `.tostring()` method)
        o Drop-in usage instead of `float` and `int` and `np.ndarray` by the
            conversion methods.
        o Basic trigonometric and hyperbolic functions are supported as methods,
            e.g. ``ev.sin()``, etc.
        o Sampling of random numbers from the Gaussian distribution described
            by the value and uncertainty fields by a single call to `.random()`
        o Evaluating complicated functions by `ErrorValue.evalfunc()`; error
            propagation is done by a Monte Carlo approach.
        o List-like indexing and slicing if ``val`` and ``err`` are arrays. Only
            read access is supported.
    """

    def __init__(self, val, err=None):
        ArithmeticBase.__init__(self)
        if isinstance(val, numbers.Number):
            self.val = float(val)
            if isinstance(err, numbers.Number):
                self.err = float(err)
            elif err is None:
                self.err = 0.0
            else:
                raise ValueError('Invalid type for error', type(err))
        elif isinstance(val, np.ndarray):
            self.val = copy.deepcopy(val)
            if isinstance(err, np.ndarray):
                assert (err.shape == val.shape)
                self.err = copy.deepcopy(err)
            elif err is None:
                self.err = np.zeros_like(self.val)
            else:
                raise ValueError('Invalid type for error', type(err))
        elif isinstance(val, ErrorValue):
            self.__init__(val.val, val.err)
        else:
            raise ValueError(
                'ErrorValue class can hold only Python numbers or numpy ndarrays, got %s!' % type(val))

        #    def __deepcopy__(self, memo):
        #        memo[self]=ErrorValue(copy.deepcopy(self.val), copy.deepcopy(self.err))
        #        return memo[self]

    def __neg__(self):
        obj = copy.deepcopy(self)
        obj.val = -obj.val
        return obj

    def _recip(self):
        """Calculate the reciprocal of this instance"""
        obj = copy.deepcopy(self)
        obj.val = 1.0 / self.val
        obj.err = (self.err / (self.val ** 2))
        return obj

    def __getitem__(self, key):
        obj = copy.deepcopy(self)
        obj.val = self.val[key]
        obj.err = self.err[key]
        return obj

    def __iadd__(self, value):
        try:
            value = ErrorValue(value)
        except ValueError:
            return NotImplemented
        self.val = self.val + value.val
        self.err = np.sqrt(self.err ** 2 + value.err ** 2)
        return self

    def __imul__(self, value):
        try:
            value = ErrorValue(value)
        except ValueError:
            return NotImplemented
        self.err = np.sqrt(self.err * self.err * value.val * value.val +
                           value.err * value.err * self.val * self.val)
        self.val = self.val * value.val
        return self

    def __str__(self):
        return self.tostring(plusminus=' \u00b1 ')

    def __pow__(self, other, modulo=None):
        if modulo is not None:
            return NotImplemented
        try:
            other = ErrorValue(other)
        except ValueError:
            return NotImplemented
        obj = copy.deepcopy(self)
        obj.err = ((self.val ** (other.val - 1) * other.val * self.err) ** 2 +
               (np.log(self.val) * self.val ** other.val * other.err) ** 2) ** 0.5
        obj.val = self.val ** other.val
        return obj

    def __repr__(self):
        return 'ErrorValue(' + repr(self.val) + ' \u00b1 ' + repr(self.err) + ')'

    def __float__(self):
        return float(self.val)

    def __trunc__(self):
        return int(self.val)

    #    def __array__(self, dt=None):
    #        if dt is None:
    #            return np.array(self.val)
    #        else:
    #            return np.array(self.val, dt)

    def tostring(self, extra_digits=0, plusminus=' \u00b1 ', fmt=None):
        """Make a string representation of the value and its uncertainty.

        Inputs:
        -------
            ``extra_digits``: integer
                how many extra digits should be shown (plus or minus, zero means
                that the number of digits should be defined by the magnitude of
                the uncertainty).
            ``plusminus``: string
                the character sequence to be inserted in place of '+/-'
                including delimiting whitespace.
            ``fmt``: string or None
                how to format the output. Currently only strings ending in 'tex'
                are supported, which render ascii-exponentials (i.e. 3.1415e-2)
                into a format which is more appropriate to TeX.

        Outputs:
        --------
            the string representation.
        """
        if isinstance(fmt, str) and fmt.lower().endswith('tex'):
            return re.subn('(\d*)(\.(\d)*)?[eE]([+-]?\d+)',
                           lambda m: (r'$%s%s\cdot 10^{%s}$' % (m.group(1), m.group(2), m.group(4))).replace('None',
                                                                                                             ''),
                           self.tostring(extra_digits=extra_digits, plusminus=plusminus, fmt=None))[0]
        if isinstance(self.val, numbers.Real):
            try:
                Ndigits = -int(math.floor(math.log10(self.err))) + extra_digits
            except (OverflowError, ValueError):
                return str(self.val) + plusminus + str(self.err)
            else:
                return str(round(self.val, Ndigits)) + plusminus + str(round(self.err, Ndigits))
        return str(self.val) + ' +/- ' + str(self.err)

    def abs(self):
        obj = copy.deepcopy(self)
        obj.val = np.abs(self.val)
        obj.err = self.err
        return obj

    def sin(self):
        obj = copy.deepcopy(self)
        obj.val = np.sin(self.val)
        obj.err = np.abs(np.cos(self.val) * self.err)
        return obj

    def cos(self):
        obj = copy.deepcopy(self)
        obj.val = np.cos(self.val)
        obj.err = np.abs(np.sin(self.val) * self.err)
        return obj

    def tan(self):
        obj = copy.deepcopy(self)
        obj.val = np.tan(self.val)
        obj.err = np.abs(1 + np.tan(self.val) ** 2) * self.err
        return obj

    def sqrt(self):
        return self ** 0.5

    def sinh(self):
        obj = copy.deepcopy(self)
        obj.val = np.sinh(self.val)
        obj.err = np.abs(np.cosh(self.val)) * self.err
        return obj

    def cosh(self):
        obj = copy.deepcopy(self)
        obj.val = np.cosh(self.val)
        obj.err = np.sinh(self.val) * self.err
        return obj

    def tanh(self):
        obj = copy.deepcopy(self)
        obj.val = np.tanh(self.val)
        obj.err = np.abs(1 - np.tanh(self.val) ** 2) * self.err
        return obj

    def arcsin(self):
        obj = copy.deepcopy(self)
        obj.val = np.arcsin(self.val)
        obj.err = np.abs(self.err / np.sqrt(1 - self.val ** 2))
        return obj

    def arccos(self):
        obj = copy.deepcopy(self)
        obj.val = np.arccos(self.val)
        obj.err = np.abs(self.err / np.sqrt(1 - self.val ** 2))
        return obj

    def arcsinh(self):
        obj = copy.deepcopy(self)
        obj.val = np.arcsinh(self.val)
        obj.err = np.abs(self.err / np.sqrt(1 + self.val ** 2))
        return obj

    def arccosh(self):
        obj = copy.deepcopy(self)
        obj.val = np.arccosh(self.val)
        obj.err = np.abs(self.err / np.sqrt(self.val ** 2 - 1))
        return obj

    def arctanh(self):
        obj = copy.deepcopy(self)
        obj.val = np.arctanh(self.val)
        obj.err = np.abs(self.err / (1 - self.val ** 2))
        return obj

    def arctan(self):
        obj = copy.deepcopy(self)
        obj.val = np.arctan(self.val)
        obj.err = np.abs(self.err / (1 + self.val ** 2))
        return obj

    def log(self):
        obj = copy.deepcopy(self)
        obj.val = np.log(self.val)
        obj.err = np.abs(self.err / self.val)
        return obj

    def exp(self):
        obj = copy.deepcopy(self)
        obj.val = np.exp(self.val)
        obj.err = np.abs(self.err * np.exp(self.val))
        return obj

    def random_sample(self):
        """Sample a random number (array) of the distribution defined by
        mean=`self.val` and variance=`self.err`^2.
        """
        if isinstance(self.val, np.ndarray):
            # IGNORE:E1103
            return np.random.randn(self.val.shape) * self.err + self.val
        else:
            return np.random.randn() * self.err + self.val

    @classmethod
    def evalfunc(cls, func, *args, **kwargs):
        """Evaluate a function with error propagation.

        Inputs:
        -------
            ``func``: callable
                this is the function to be evaluated. Should return either a
                number or a np.ndarray.
            ``*args``: other positional arguments of func. Arguments which are
                not instances of `ErrorValue` are taken as constants.

            keyword arguments supported:
                ``NMC``: number of Monte-Carlo steps. If not defined, defaults
                to 1000
                ``exceptions_to_retry``: list of exception types to ignore:
                    if one of these is raised the given MC step is repeated once
                    again. Notice that this might induce an infinite loop!
                    The exception types in this list should be subclasses of
                    ``Exception``.
                ``exceptions_to_skip``: list of exception types to skip: if
                    one of these is raised the given MC step is skipped, never
                    to be repeated. The exception types in this list should be
                    subclasses of ``Exception``.


        Output:
        -------
            ``result``: an `ErrorValue` with the result. The error is estimated
                via a Monte-Carlo approach to Gaussian error propagation.
        """

        def do_random(x):
            if isinstance(x, cls):
                return x.random_sample()
            else:
                return x

        if 'NMC' not in kwargs:
            kwargs['NMC'] = 1000
        if 'exceptions_to_skip' not in kwargs:
            kwargs['exceptions_to_skip'] = []
        if 'exceptions_to_repeat' not in kwargs:
            kwargs['exceptions_to_repeat'] = []
        meanvalue = func(*args)
        # this way we get either a number or a np.array
        stdcollector = meanvalue * 0
        mciters = 0
        while mciters < kwargs['NMC']:
            try:
                # IGNORE:W0142
                stdcollector += (func(*[do_random(a)
                                        for a in args]) - meanvalue) ** 2
                mciters += 1
            except Exception as e:  # IGNORE:W0703
                if any(isinstance(e, etype) for etype in kwargs['exceptions_to_skip']):
                    kwargs['NMC'] -= 1
                elif any(isinstance(e, etype) for etype in kwargs['exceptions_to_repeat']):
                    pass
                else:
                    raise
        return cls(meanvalue, stdcollector ** 0.5 / (kwargs['NMC'] - 1))

    def is_zero(self):
        return np.abs(self.val) <= np.abs(self.err)

    @classmethod
    def average_independent(cls, lis):
        if not all([isinstance(x, cls) for x in lis]):
            raise ValueError(
                'All elements of the list should be of the same type: ' + str(cls))
        return cls(sum([x.val / x.err ** 2 for x in lis]) / sum([1 / x.err ** 2 for x in lis]),
                   1 / sum([1 / x.err ** 2 for x in lis]) ** 0.5)

    def __bool__(self):
        return not self.is_zero()
