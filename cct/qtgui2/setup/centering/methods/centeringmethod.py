# coding: utf-8
"""Base class for centering methods"""

from typing import Union

from .....core2.dataclasses.exposure import Exposure
import numpy as np
from matplotlib.axes import Axes


class CenteringMethod:
    """Base class for beam centering methods"""
    name: str
    description: str
    patternaxes: Axes
    curveaxes: Axes
    polaraxes: Axes


    def __init__(self, **kwargs):
        self.patternaxes = kwargs.pop('patternaxes')
        self.curveaxes = kwargs.pop('curveaxes')
        self.polaraxes = kwargs.pop('polaraxes')

    def goodnessfunction(self, exposure: Exposure, beamx: Union[float, np.ndarray], beamy:Union[float, np.ndarray]):
        raise NotImplementedError

    def run(self):
        raise NotImplementedError
