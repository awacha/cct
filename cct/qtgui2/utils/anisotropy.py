import logging

import numpy as np
from PyQt5 import QtWidgets, QtGui
from matplotlib.axes import Axes
from matplotlib.patches import Circle, Polygon
from matplotlib.widgets import SpanSelector

from .anisotropy_ui import Ui_Form
from .fsnselector import FSNSelector
from .h5selector import H5Selector
from .plotimage import PlotImage
from .window import WindowRequiresDevices
from ...core2.algorithms.radavg import maskforannulus, maskforsectors
from ...core2.dataclasses import Exposure

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AnisotropyEvaluator(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    plotimage: PlotImage
    axes_full: Axes
    axes_azim: Axes
    axes_slice: Axes
    vboxLayout: QtWidgets.QVBoxLayout
    fsnSelector: FSNSelector
    h5Selector: H5Selector
    fullSpanSelector: SpanSelector
    azimSpanSelector: SpanSelector
    exposure: Exposure

    def __init__(self, *args, **kwargs):
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        self._circles = []
        self._slicelines = []
        self._slicearcs = []
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.setWindowTitle('Anisotropy Evaluator [*]')
        self.plotimage = PlotImage(self)
        self.plotimage.figure.clf()
        self.plotimage.axes = self.plotimage.figure.add_subplot(2, 2, 1)
        self.plotimage.axes.set_facecolor('black')
        self.plotimage.axes.set_title('2D scattering pattern')
        self.plotimage.axesComboBox.setCurrentIndex(self.plotimage.axesComboBox.findText('q'))
        self.axes_full = self.plotimage.figure.add_subplot(2, 2, 2)
        self.axes_azim = self.plotimage.figure.add_subplot(2, 2, 3)
        self.axes_slice = self.plotimage.figure.add_subplot(2, 2, 4)
        self.vboxLayout = QtWidgets.QVBoxLayout()
        self.vboxLayout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.vboxLayout)
        if self.instrument is not None:
            self.fsnSelector = FSNSelector(self)
            self.vboxLayout.addWidget(self.fsnSelector)
            self.fsnSelector.FSNSelected.connect(self.onFSNSelected)
        self.h5Selector = H5Selector(self)
        self.vboxLayout.addWidget(self.h5Selector)
        self.h5Selector.datasetSelected.connect(self.onH5Selected)
        self.vboxLayout.addWidget(self.plotimage, stretch=1)
        self.plotimage.figure.tight_layout()
        self.plotimage.canvas.draw()

    def onFSNSelected(self, prefix: str, fsn: int):
        self.setExposure(self.fsnSelector.loadExposure())

    def onH5Selected(self, filename: str, sample: str, distance: float):
        self.setExposure(self.h5Selector.loadExposure())

    def setExposure(self, exposure: Exposure):
        self.exposure = exposure
        self.removeCircles()
        self.removeSliceLines()
        self.axes_azim.clear()
        self.axes_slice.clear()
        self.plotimage.setExposure(exposure)
        self.axes_full.clear()
        rad = exposure.radial_average()
        self.axes_full.loglog(rad.q, rad.intensity, label='Full radial average')
        self.axes_full.set_xlabel('q (nm$^{-1}$)')
        self.axes_full.set_ylabel(r'$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
        self.axes_full.set_title('Circular average')
        self.axes_full.set_xlabel('q (nm$^{-1}$)')
        self.axes_full.set_ylabel(r'$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
        self.fullSpanSelector = SpanSelector(self.axes_full, self.onQRangeSelected, 'horizontal', span_stays=True)
        self.axes_azim.set_xlabel(r'$\phi$ (°)')
        self.axes_azim.set_ylabel(r'$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
        self.axes_azim.set_title('Azimuthal scattering curve')
        self.axes_slice.set_xlabel('q (nm$^{-1}$)')
        self.axes_slice.set_ylabel(r'$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
        self.axes_slice.set_title('Slices')
        self.plotimage.figure.tight_layout()
        self.plotimage.canvas.draw()

    def resizeEvent(self, a0: QtGui.QResizeEvent):
        self.plotimage.figure.tight_layout()
        return super().resizeEvent(a0)

    def removeCircles(self):
        for c in self._circles:
            c.remove()
        self._circles = []

    def removeSliceLines(self):
        for l in self._slicelines:
            l.remove()
        self._slicelines = []
        for a in self._slicearcs:
            a.remove()
        self._slicearcs = []

    def onQRangeSelected(self, qmin: float, qmax: float):
        self.removeCircles()
        self.removeSliceLines()
        self._circles = [
            Circle((0, 0), radius=qmin, color='white', fill=False, linestyle='--', zorder=100),
            Circle((0, 0), radius=qmax, color='white', fill=False, linestyle='--', zorder=100)
        ]
        self.plotimage.axes.add_patch(self._circles[0])
        self.plotimage.axes.add_patch(self._circles[1])
        self.plotimage.canvas.draw()
        ex = self.exposure
        # ex.mask_nonfinite()
        prevmask = ex.mask
        logger.debug(f'{qmin=}, {qmax=}, pixmin={ex.qtopixel(qmin)}, pixmax={ex.qtopixel(qmax)}')
        try:
            ex.mask = maskforannulus(mask=ex.mask, center_row=ex.header.beamposrow[0],
                                     center_col=ex.header.beamposcol[0], pixmin=ex.qtopixel(qmin),
                                     pixmax=ex.qtopixel(qmax))
            azimcurve = ex.azim_average(100).sanitize()
            logger.debug(f'{ex.mask.sum()=}')
        finally:
            ex.mask = prevmask
        self.axes_azim.clear()
        self.axes_azim.plot(azimcurve.phi * 180.0 / np.pi, azimcurve.intensity, label='Azimuthal curve')
        self.plotimage.canvas.draw()
        self.azimSpanSelector = SpanSelector(self.axes_azim, self.onPhiRangeSelected, 'horizontal', span_stays=True)
        self.axes_azim.set_xlabel(r'$\phi$ (°)')
        self.axes_azim.set_ylabel(r'$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
        self.axes_azim.set_title('Azimuthal scattering curve')

    def onPhiRangeSelected(self, phimin: float, phimax: float):
        ex = self.exposure
        phi0 = (phimin + phimax) * 0.5
        dphi = (phimax - phimin)
        prevmask = ex.mask
        ex.mask = maskforsectors(ex.mask, ex.header.beamposrow[0], ex.header.beamposcol[0], phi0 * np.pi / 180.,
                                 dphi * np.pi / 180, symmetric=True)
        try:
            sliced = ex.radial_average().sanitize()
        finally:
            ex.mask = prevmask
        line2d = self.axes_slice.loglog(
            sliced.q, sliced.intensity,
            label=rf'$\phi_0={phi0:.2f}^\circ$, $\Delta\phi = {dphi:.2f}^\circ$')[0]
        self.axes_slice.legend(loc='best')
        self.axes_slice.set_title('Slices')
        qmax = np.nanmax(ex.q()[0])
        ax = self.plotimage.axes.axis()
        points = np.zeros((101, 2), np.double)
        points[0, :] = 0
        phi = np.linspace(phimin, phimax, 100) * np.pi / 180.
        points[1:101, 0] = qmax * np.sin(phi)
        points[1:101, 1] = qmax * np.cos(phi)
        self._slicearcs.extend([
            Polygon(points, closed=True, color=line2d.get_color(), zorder=100, alpha=0.5, linewidth=1, fill=True),
            Polygon(-points, closed=True, color=line2d.get_color(), zorder=100, alpha=0.5, linewidth=1, fill=True)
        ])
        self.plotimage.axes.add_patch(self._slicearcs[-1])
        self.plotimage.axes.add_patch(self._slicearcs[-2])
        self.plotimage.axes.axis(ax)
        self.plotimage.canvas.draw_idle()