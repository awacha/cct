# coding: utf-8
"""Beam position finding algorithm using sector averages of the scattering pattern"""

from typing import Union, Optional

import numpy as np
from PySide6.QtCore import Slot
from matplotlib.widgets import SpanSelector

from .centeringmethod import CenteringMethod
from .sectors_ui import Ui_Form
from .....core2.algorithms.radavg import fastradavg, maskforannulus, maskforsectors
from .....core2.dataclasses.exposure import Exposure


class Sector(CenteringMethod, Ui_Form):
    name = 'Sectors'
    description = 'Find beam center by aligning sector averages'
    polarspanselector: Optional[SpanSelector] = None
    curvespanselector: Optional[SpanSelector] = None

    def prepareUI(self, exposure: Exposure):
        if exposure is not None:
            self.pixMinDoubleSpinBox.setValue(0.0)
            self.pixMaxDoubleSpinBox.setValue((exposure.shape[0] ** 2 + exposure.shape[1] ** 2) ** 0.5)
        self.polarspanselector = SpanSelector(
            self.polaraxes, self.onSpanSelected, 'horizontal', useblit=True,
                                         props={'alpha': 0.3, 'color': 'red', 'hatch': 'xxx'}, interactive=True)
        self.polarspanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())
        self.polarspanselector.active = True
        self.curvespanselector = SpanSelector(self.curveaxes, self.onSpanSelected, 'horizontal', useblit=True,
                                              props={'alpha': 0.3, 'color': 'red', 'hatch': 'xxx'}, interactive=True)
        self.curvespanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())
        self.curvespanselector.active = True

    def goodnessfunction(self, beamrow: Union[float, np.ndarray], beamcol: Union[float, np.ndarray],
                         exposure: Exposure):
        pixmin = self.pixMinDoubleSpinBox.value()
        pixmax = self.pixMaxDoubleSpinBox.value()
        npix = self.radBinCountSpinBox.value()
        nsector = self.sectorCountSpinBox.value()
        if np.isscalar(beamrow):
            beamrow = np.array([beamrow])
        if np.isscalar(beamcol):
            beamcol = np.array([beamcol])
        if beamrow.shape != beamcol.shape:
            raise ValueError('Arguments `beamx` and `beamy` must have the same shape')
        mask = exposure.mask.astype(np.uint8)
        gof = []
        for br, bc in zip(beamrow.ravel(), beamcol.ravel()):
            mask_annulus = maskforannulus(mask, br, bc, pixmin, pixmax)
            mask_sector = [
                maskforsectors(mask_annulus, br, bc, 2 * np.pi / nsector * i, np.pi / nsector) for i in range(nsector)
            ]
            rad = [fastradavg(exposure.intensity, m, br, bc, pixmin, pixmax, npix) for m in
                   mask_sector]
            intensities = np.stack([intensity for pix, intensity, area in rad], axis=1)
            gof.append(np.nansum(np.nanstd(intensities, axis=1)))
        return np.array(gof).reshape(beamrow.shape)

    def cleanupUI(self):
        if self.polarspanselector is not None:
            self.polarspanselector.active = False
        if self.curvespanselector is not None:
            self.curvespanselector.active = False
        self.polarspanselector = None
        self.curvespanselector = None

    def onSpanSelected(self, pixmin, pixmax):
        self.pixMinDoubleSpinBox.setValue(pixmin)
        self.pixMaxDoubleSpinBox.setValue(pixmax)

    @Slot(float, name='on_pixMinDoubleSpinBox_valueChanged')
    @Slot(float, name='on_pixMaxDoubleSpinBox_valueChanged')
    def updateSpanSelector(self, value: float):
        if self.polarspanselector is not None:
            self.polarspanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())
        if self.curvespanselector is not None:
            self.curvespanselector.extents = (self.pixMinDoubleSpinBox.value(), self.pixMaxDoubleSpinBox.value())
