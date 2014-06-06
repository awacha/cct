# pylint: disable=W0401

import searchpath
import pathutils
import pauser
import utils
import easylsq
import basicfit
import rc
import errorvalue
import arithmetic
import numerictests
import matplotlib_scales

from searchpath import *
from pathutils import *
from pauser import *
from utils import *
from easylsq import *
from basicfit import *
from errorvalue import *
from arithmetic import *
from numerictests import *
from rc import sastoolrc

class SASException(BaseException):
    "General exception class for the package `sastool`"
    pass

__all__ = ['arithmetic', 'basicfit', 'easylsq', 'errorvalue', 'pathutils',
           'pauser', 'rc', 'searchpath', 'utils']

for k in __all__[:]:
    __all__.extend(eval('%s.__all__' % k))
