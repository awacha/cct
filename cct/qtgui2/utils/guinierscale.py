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

    def __init__(self, axis):
        super().__init__(axis)
        self._transform = GuinierForwardTransform()

    def get_transform(self):
        return self._transform

    def limit_range_for_scale(self, vmin, vmax, minpos):
        logger.debug(f'limit_range_for_scale({vmin=}, {vmax=}, {minpos=}')
        if not np.isfinite(minpos) or minpos <= 0:
            minpos = 1e-7
        return (minpos if vmin <= 0 else vmin), (minpos if vmax <= 0 else vmax)

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
    def transform(self, values):
        logger.debug(f'GuinierForwardTransform {values}, {self.input_dims=}')
        return super().transform(values)

    def transform_non_affine(self, values):
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.ma.power(values, 2)

    def inverted(self):
        return GuinierBackwardTransform()


class GuinierBackwardTransform(Transform):
    def transform(self, values):
        logger.debug(f'GuinierBackwardTransform {values}, {self.input_dims=}')
        return super().transform(values)

    def transform_non_affine(self, values):
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.ma.power(values, 0.5)

    def inverted(self):
        return GuinierForwardTransform()


matplotlib.scale.register_scale(GuinierScale)
