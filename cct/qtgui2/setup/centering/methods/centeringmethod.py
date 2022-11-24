# coding: utf-8
"""Base class for centering methods"""

import logging
from typing import Union, List, Type

import lmfit
import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Signal
from matplotlib.axes import Axes

from .....core2.dataclasses.exposure import Exposure


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class CenteringMethod(QtWidgets.QWidget):
    """Base class for beam centering methods"""
    name: str
    description: str
    patternaxes: Axes
    curveaxes: Axes
    polaraxes: Axes
    positionFound = Signal(float, float, float, float, name='positionFound')

    def __init__(self, **kwargs):
        self.patternaxes = kwargs.pop('patternaxes')
        self.curveaxes = kwargs.pop('curveaxes')
        self.polaraxes = kwargs.pop('polaraxes')
        super().__init__(**kwargs)
        self.setupUi(self)

    def goodnessfunction(self, beamrow: Union[float, np.ndarray], beamcol: Union[float, np.ndarray],
                         exposure: Exposure):
        raise NotImplementedError

    def run(self, exposure: Exposure) -> lmfit.minimizer.MinimizerResult:
        scalefactor = 1
        params = lmfit.Parameters()
        params.add('br_scaled', exposure.header.beamposrow[0] / scalefactor, vary=True)
        params.add('bc_scaled', exposure.header.beamposcol[0] / scalefactor, vary=True)
        params.add('beamrow', vary=False, expr = f'br_scaled * {scalefactor:g}')
        params.add('beamcol', vary=False, expr = f'bc_scaled * {scalefactor:g}')

        def targetfcn(params: lmfit.Parameters, exposure: Exposure):
            parvals = params.valuesdict()
            gfunc = self.goodnessfunction(parvals['beamrow'], parvals['beamcol'], exposure=exposure)[0]
            logger.debug(f'{parvals["beamrow"]}, {parvals["beamcol"]} -> {gfunc}')
            return gfunc

        minimized = lmfit.minimize(targetfcn, params, method='nelder', kws={'exposure': exposure}, calc_covar=True)
        return minimized

    def prepareUI(self, exposure: Exposure):
        """Adjust UI elements (set limits of spin boxes etc.) when this method becomes active or a new exposure is
        loaded"""
        raise NotImplementedError

    def cleanupUI(self):
        """Cleans up various tweaks which we have made to the image, scattering curve and azimuthal images.

        Should tolerate multiple calling (even if there was no prepareUI() before).
        """
        raise NotImplementedError

    @classmethod
    def allMethods(cls) -> List[Type["CenteringMethod"]]:
        lis = []
        try:
            if isinstance(cls.name, str):
                lis.append(cls)
        except AttributeError:
            pass
        for subcls in cls.__subclasses__():
            lis.extend(subcls.allMethods())
        return lis
