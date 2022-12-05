# coding: utf-8
"""Peak height centering method"""
from typing import Union, Optional, Final
import logging

import lmfit
import numpy as np
from PySide6.QtCore import Slot
from matplotlib.widgets import SpanSelector

from .centeringmethod import CenteringMethod
from .peakheight_ui import Ui_Form
from .....core2.algorithms.radavg import fastradavg
from .....core2.dataclasses.exposure import Exposure

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class PeakFitting(CenteringMethod, Ui_Form):
    name = None
    description = None
    polarspanselector: Optional[SpanSelector] = None
    curvespanselector: Optional[SpanSelector] = None
    mode: Optional[str] = None

    def setupUi(self, Form):
        super().setupUi(Form)

    def goodnessfunction(self, beamrow: Union[float, np.ndarray], beamcol: Union[float, np.ndarray],
                         exposure: Exposure) -> np.ndarray:
        pixmin = self.pixMinDoubleSpinBox.value()
        pixmax = self.pixMaxDoubleSpinBox.value()
        npix = int(
            abs(pixmax - pixmin)) if self.pixelCountSpinBox.value() == self.pixelCountSpinBox.minimum() else self.pixelCountSpinBox.value()
        image = exposure.intensity
        mask = exposure.mask.astype(np.uint8)
        if np.isscalar(beamrow):
            beamrow = np.array([beamrow])
        if np.isscalar(beamcol):
            beamcol = np.array([beamcol])
        if beamrow.shape != beamcol.shape:
            raise ValueError('Arguments `beamx` and `beamy` must have the same shape')
        if self.peakFunctionComboBox.currentText() == 'Gaussian':
            model = lmfit.Model(self._gaussian)
        elif self.peakFunctionComboBox.currentText() == 'Lorentzian':
            model = lmfit.Model(self._lorentzian)
        else:
            assert False
        params = model.make_params()
        gof = []
        for br, bc in zip(beamrow, beamcol):
            pixel, intensity, area = fastradavg(image, mask, br, bc, pixmin, pixmax, npix)
            params['A'].value = intensity.max()
            params['bg'].value = intensity.min()
            params['fwhm'].value = pixel.max() - pixel.min()
            params['pos'].value = intensity[np.argmax(intensity)]
            params['A'].vary = False
            params['bg'].vary = False
            params['pos'].vary = False
            result = model.fit(intensity, params, x=pixel)
            params = result.params
            params['A'].vary = True
            params['bg'].vary = True
            params['pos'].vary = True
            result = model.fit(intensity, params, x=pixel)
            if self.mode == 'height':
                gof.append(- (result.params['A'].value + result.params['bg'].value))
            else:
                gof.append(result.params['fwhm'])
        return np.array(gof)

    def prepareUI(self, exposure: Exposure):
        self.setEnabled(exposure is not None)
        if exposure is None:
            return
        self.curvespanselector = SpanSelector(
            self.curveaxes, self.onRangeSelected, 'horizontal', useblit=True, interactive=True,
            props={'alpha': 0.3, 'facecolor': 'red', 'hatch': '///', 'fill': False})
        self.polarspanselector = SpanSelector(
            self.polaraxes, self.onRangeSelected, 'horizontal', useblit=True, interactive=True,
            props={'alpha': 0.3, 'facecolor': 'red', 'hatch': '///', 'fill': False})
        pixmin, pixmax = exposure.validpixelrange()
        self.pixMinDoubleSpinBox.setRange(pixmin, pixmax)
        self.pixMaxDoubleSpinBox.setRange(pixmin, pixmax)
        self.pixMinDoubleSpinBox.setValue(pixmin)
        self.pixMaxDoubleSpinBox.setValue(pixmax)
        self.curvespanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())
        self.curvespanselector.active = True
        self.polarspanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())
        self.polarspanselector.active = True

    def cleanupUI(self):
        if self.polarspanselector is not None:
            self.polarspanselector.active = False
            self.polarspanselector = None
        if self.curvespanselector is not None:
            self.curvespanselector.active = False
            self.curvespanselector = None
        pass

    def onRangeSelected(self, pixmin, pixmax):
        logger.debug(f'onRangeSelected({pixmin=}, {pixmax=})')
        self.pixMinDoubleSpinBox.setValue(pixmin)
        self.pixMaxDoubleSpinBox.setValue(pixmax)

    @Slot(float, name='on_pixMinDoubleSpinBox_valueChanged')
    def on_pixMinDoubleSpinBox_valueChanged(self, value: float):
        logger.debug(f'on_pixMinMaxDoubleSpinBox_valueChanged({value=})')
        self.polarspanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())
        self.curvespanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())

    @Slot(float, name='on_pixMaxDoubleSpinBox_valueChanged')
    def on_pixMaxDoubleSpinBox_valueChanged(self, value: float):
        logger.debug(f'on_pixMinMaxDoubleSpinBox_valueChanged({value=})')
        self.polarspanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())
        self.curvespanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())

    @staticmethod
    def _gaussian(x, A, pos, fwhm, bg):
        sigma = fwhm / (2 * (2 * np.log(2)) ** 0.5)
        return A * np.exp(-(x - pos) ** 2 / (2 * sigma ** 2)) + bg

    @staticmethod
    def _lorentzian(x, A, pos, fwhm, bg):
        gamma = fwhm / 2
        return A / (1 + ((x - pos) / gamma) ** 2) + bg


class PeakHeight(PeakFitting):
    mode: Final[str] = 'height'
    description: Final[str] = 'Find beam center by maximizing the height of a peak in the scattering curve'
    name: Final[str] = 'Peak height'


class PeakWidth(PeakFitting):
    mode: Final[str] = 'width'
    description: Final[str] = 'Find beam center by minimizing the width of a peak in the scattering curve'
    name: Final[str] = 'Peak width'
