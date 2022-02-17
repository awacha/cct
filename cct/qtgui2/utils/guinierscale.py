# coding: utf-8
"""
Matplotlib scale for Guinier plots
"""
import matplotlib.ticker
from matplotlib.scale import ScaleBase
from matplotlib.transforms import Transform
import numpy as np


class GuinierScale(ScaleBase):
    """
    Horizontal scale for Guinier plots, i.e. log(I) vs. q^2
    """
    name = 'Guinier'

    def __init__(self, axis):
        super().__init__(axis)
        self._transform = GuinierForwardTransform()

    def get_transform(self):
        return self._transform

    def limit_range_for_scale(self, vmin, vmax, minpos):
        if not np.isfinite(minpos) or minpos<=0:
            minpos = 1e-7
        return max(vmin, minpos), vmax

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
    def transform_non_affine(self, values):
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.ma.power(values, 2)

    def inverted(self):
        return GuinierBackwardTransform()


class GuinierBackwardTransform(Transform):
    def transform_non_affine(self, values):
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.ma.power(values, 0.5)

    def inverted(self):
        return GuinierForwardTransform()


matplotlib.scale.register_scale(GuinierScale)
