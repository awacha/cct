# coding: utf-8
"""
Matplotlib scale for Guinier plots
"""
import logging

import matplotlib.ticker
import numpy as np
from matplotlib.scale import ScaleBase
from matplotlib.transforms import Transform

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GuinierScale(ScaleBase):
    """
    Horizontal scale for Guinier plots, i.e. log(I) vs. q^2
    """
    name = 'guinier'

    def __init__(self, axis, *, minpos=1e-7):
        self._default_minpos = minpos
        super().__init__(axis)
        self._transform = GuinierForwardTransform()

    def get_transform(self):
        return self._transform

    def limit_range_for_scale(self, vmin, vmax, minpos):
        return vmin, vmax

    def set_default_locators_and_formatters(self, axis):
        axis.set_major_locator(matplotlib.ticker.AutoLocator())
        axis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
        axis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        if ((axis.axis_name == 'x' and matplotlib.rcParams['xtick.minor.visible']) or
                (axis.axis_name == 'y' and matplotlib.rcParams['ytick.minor.visible'])):
            axis.set_minor_locator(matplotlib.ticker.AutoMinorLocator())
        else:
            axis.set_minor_locator(matplotlib.ticker.NullLocator())


class GuinierForwardTransform(Transform):
    input_dims = 1
    output_dims = 1

    def transform_non_affine(self, values):
        transformed = np.zeros_like(values)
        idxnonfinite = ~np.isfinite(values)
        idxnonnegative = np.logical_and(~idxnonfinite, values >= 0)
        idxnegative = np.logical_and(~idxnonfinite, values < 0)
        transformed[idxnonfinite] = np.nan
        transformed[idxnonnegative] = values[idxnonnegative] ** 2
        transformed[idxnegative] = - values[idxnegative] ** 2
        return transformed

    def inverted(self):
        return GuinierBackwardTransform()


class GuinierBackwardTransform(Transform):
    input_dims = 1
    output_dims = 1

    def transform_non_affine(self, values):
        transformed = np.zeros_like(values)
        idxnonfinite = ~np.isfinite(values)
        idxnonnegative = np.logical_and(~idxnonfinite, values >= 0)
        idxnegative = np.logical_and(~idxnonfinite, values < 0)
        transformed[idxnonfinite] = np.nan
        transformed[idxnonnegative] = values[idxnonnegative] ** 0.5
        transformed[idxnegative] = - (-values[idxnegative]) ** 0.5
        return transformed

    def inverted(self):
        return GuinierForwardTransform()


matplotlib.scale.register_scale(GuinierScale)
