import logging
from typing import Optional, Final, List
import sys

import matplotlib
import matplotlib.cm
import matplotlib.colors
import numpy as np
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Slot
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.colorbar import Colorbar
from matplotlib.figure import Figure
from matplotlib.image import AxesImage
from matplotlib.lines import Line2D

from .plotimage_ui import Ui_Form
from ...core2.dataclasses import Exposure

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

maskcmap = matplotlib.colors.ListedColormap([(0.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.7)])


class PlotImage(QtWidgets.QWidget, Ui_Form):
    figure: Figure = None
    canvas: FigureCanvasQTAgg = None
    figToolbar: NavigationToolbar2QT = None
    axes: Axes = None
    mask: Optional[np.ndarray] = None
    matrix: Optional[np.ndarray] = None
    beamx: Optional[float] = None
    beamy: Optional[float] = None
    pixelsize: Optional[float] = None
    distance: Optional[float] = None
    wavelength: Optional[float] = None
    title: Optional[str] = None

    _cmapaxis: Optional[Colorbar] = None
    _imghandle: Optional[AxesImage] = None
    _maskhandle: Optional[AxesImage] = None
    _xcrosshairhandle: Optional[Line2D] = None
    _ycrosshairhandle: Optional[Line2D] = None

    _strictlypositivenormalizations: Final[List[str]] = ['log10', 'square', 'sqrt']

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.mask = None
        self.matrix = None
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(figsize=(2, 1.5), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figToolbar = NavigationToolbar2QT(self.canvas, self)
        self.layout().addWidget(self.figToolbar)
        self.layout().addWidget(self.canvas, 1)
        self.canvas.mpl_connect('resize_event', self.onCanvasResize)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
            QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        gs = self.figure.add_gridspec(1, 1)
        self.axes = self.figure.add_subplot(gs[:, :])
        self.axes.set_facecolor('black')
        self.axes.set_anchor((0.5, 0.5))
        self.canvas.draw_idle()
        cmapnames = list(matplotlib.cm.cmaps_listed) + list(matplotlib.cm.datad)
        self.paletteComboBox.addItems(sorted(cmapnames + [f'{cmname}_r' for cmname in cmapnames]))
        self.paletteComboBox.setCurrentIndex(self.paletteComboBox.findText(matplotlib.rcParams['image.cmap']))
        self.paletteComboBox.currentIndexChanged.connect(self.onPaletteChanged)
        self.colourScaleComboBox.currentIndexChanged.connect(self.onColourScaleChanged)
        self.axesComboBox.currentIndexChanged.connect(self.axisScaleChanged)
        self.showColourBarToolButton.toggled.connect(self.showColourBar)
        self.showBeamToolButton.toggled.connect(self.showBeam)
        self.showMaskToolButton.toggled.connect(self.showMask)
        self.equalAspectToolButton.toggled.connect(self.changeAspect)
        self.lockZoomToolButton.toggled.connect(self.onLockZoomToggled)

    @Slot(bool)
    def onLockZoomToggled(self, active: bool):
        self.lockZoomToolButton.setIcon(
            QtGui.QIcon(QtGui.QPixmap(":/icons/zoom_locked.svg" if active else ":/icons/zoom_unlocked.svg")))

    @Slot()
    def axisScaleChanged(self):
        if self.matrix is None:
            return
        self.replot()
        (left, right, bottom, top), center = self._get_extent()
        self.axes.axis([left, right, bottom, top])
        self.canvas.draw_idle()
        self.figToolbar.update()

    @Slot(bool)
    def showColourBar(self, showit: bool):
        if self._cmapaxis is not None:
            self._cmapaxis.ax.set_visible(showit)
            self.canvas.draw_idle()

    @Slot(bool)
    def showMask(self, showit: bool):
        if self._maskhandle is not None:
            self._maskhandle.set_visible(showit)
            self.canvas.draw_idle()

    @Slot(bool)
    def showBeam(self, showit: bool):
        if self._xcrosshairhandle is not None:
            self._xcrosshairhandle.set_visible(showit)
            self.canvas.draw_idle()
        if self._ycrosshairhandle is not None:
            self._ycrosshairhandle.set_visible(showit)
            self.canvas.draw_idle()

    @Slot(bool)
    def changeAspect(self, equalaspect: bool):
        self.axes.set_aspect('equal' if equalaspect else 'auto')
        self.canvas.draw_idle()

    def onCanvasResize(self, event):
        pass

    def _get_extent(self):
        # extent: left, right, bottom, top
        if self.axesComboBox.currentText() == 'abs. pixel':
            extent = (
                -0.5,
                self.matrix.shape[1] - 0.5,
                self.matrix.shape[0] - 0.5,
                -0.5)
            center = (self.beamx, self.beamy)
        elif self.axesComboBox.currentText() == 'rel. pixel':
            extent = (-0.5 - self.beamx,
                      self.matrix.shape[1] - self.beamx - 0.5,
                      self.matrix.shape[0] - self.beamy - 0.5,
                      -0.5 - self.beamy)
            center = (0.0, 0.0)
        elif self.axesComboBox.currentText() == 'detector radius':
            extent = ((-0.5 - self.beamx) * self.pixelsize,
                      (self.matrix.shape[1] - self.beamx - 0.5) * self.pixelsize,
                      (self.matrix.shape[0] - self.beamy - 0.5) * self.pixelsize,
                      (-0.5 - self.beamy) * self.pixelsize)
            center = (0.0, 0.0)
        elif self.axesComboBox.currentText() == 'twotheta':
            extent = (
                180 / np.pi * np.arctan((-0.5 - self.beamx) * self.pixelsize / self.distance),
                180 / np.pi * np.arctan((self.matrix.shape[1] - self.beamx - 0.5) * self.pixelsize / self.distance),
                180 / np.pi * np.arctan((self.matrix.shape[0] - self.beamy - 0.5) * self.pixelsize / self.distance),
                180 / np.pi * np.arctan((-0.5 - self.beamy) * self.pixelsize / self.distance),
            )
            center = (0.0, 0.0)
        elif self.axesComboBox.currentText() == 'q':
            extent = (
                4 * np.pi * np.sin(
                    0.5 * np.arctan(
                        (-0.5 - self.beamx) * self.pixelsize / self.distance)) / self.wavelength,
                4 * np.pi * np.sin(
                    0.5 * np.arctan(
                        (self.matrix.shape[1] - self.beamx - 0.5) * self.pixelsize / self.distance)) / self.wavelength,
                4 * np.pi * np.sin(
                    0.5 * np.arctan(
                        (self.matrix.shape[0] - self.beamy - 0.5) * self.pixelsize / self.distance)) / self.wavelength,
                4 * np.pi * np.sin(
                    0.5 * np.arctan(
                        (-0.5 - self.beamy) * self.pixelsize / self.distance)) / self.wavelength,
            )
            center = (0.0, 0.0)
        else:
            assert False
        return extent, center

    @Slot(int)
    def onColourScaleChanged(self, index: int):
        self.replot()

    @Slot(int)
    def onPaletteChanged(self, index: int):
        self.replot()

    def replot(self, keepzoom: Optional[bool] = None):
        if keepzoom is None:
            logger.debug(f'Defaulting keepzoom to {self.lockZoomToolButton.isChecked()}')
            keepzoom = self.lockZoomToolButton.isChecked()
        logger.debug(f'Replotting: keeping zoom: {keepzoom}')
        if self.matrix is None:
            return
        extent, center = self._get_extent()
        # now plot the matrix
        axlimits = self.axes.axis()
        if self.colourScaleComboBox.currentText() in self._strictlypositivenormalizations:
            matrix = self.matrix.copy()
            matrix[matrix <= 0] = np.nan
        else:
            matrix = self.matrix
        if self._imghandle is None:
            keepzoom = False
        else:
            self._imghandle.remove()
        norm = self.getNormalization()
        logger.debug(f'Using normalization {norm}, vmin is {norm.vmin}, vmax is {norm.vmax}')
        self._imghandle = self.axes.imshow(
            matrix,
            cmap=self.paletteComboBox.currentText(),
            norm=norm,
            aspect='equal' if self.equalAspectToolButton.isChecked() else 'auto',
            interpolation='nearest',
            alpha=1.0,
            origin='upper',
            extent=extent,
            picker=True,
        )
        if self._cmapaxis is not None:
            self._cmapaxis.norm = self._imghandle.norm
            self._cmapaxis.vmin = self._imghandle.norm.vmin
            self._cmapaxis.vmax = self._imghandle.norm.vmax
#                self._cmapaxis.update_normal(self._imghandle)
        # color bar
        if np.ma.core.is_masked(self._imghandle.norm.vmin) or np.ma.core.is_masked(self._imghandle.norm.vmax):
            # we won't be able to make a color bar
            if self._cmapaxis is None:
                # keep it that way
                pass
            else:
                self._cmapaxis.remove()
                self._cmapaxis = None
        else:
            try:
                if self._cmapaxis is None:
                    self._cmapaxis = self.figure.colorbar(
                        self._imghandle,
                        cax=self._cmapaxis.ax if self._cmapaxis is not None else None,
                        ax=None if self._cmapaxis is not None else self.axes,
                    )
                self._cmapaxis.ax.set_visible(self.showColourBarToolButton.isChecked())
            except ZeroDivisionError:
                self._cmapaxis = None
                pass
        self.axes.set_anchor((0.5, 0.5))
        if self._cmapaxis is not None:
            self._cmapaxis.ax.set_anchor((0, 0.5))
        # now plot the mask
        logger.debug(f'Mask: {(self.mask != 0).sum()} nonzero, {(self.mask == 0).sum()} zero pixels')
        if self._maskhandle is not None:
            self._maskhandle.remove()
        self._maskhandle = self.axes.imshow(
            self.mask,
            cmap=maskcmap,
            aspect='equal' if self.equalAspectToolButton.isChecked() else 'auto',
            interpolation='nearest',
            norm=matplotlib.colors.Normalize(0, 1),
            # alpha=0.7,  # no need to specify: the color map does the job.
            origin='upper',
            extent=extent,
        )
        self._maskhandle.set_visible(self.showMaskToolButton.isChecked())

        # plot the crosshair
        if self._xcrosshairhandle is None:
            self._xcrosshairhandle = self.axes.axhline(center[1], color='w', ls='--', lw=0.5)
        else:
            self._xcrosshairhandle.set_ydata([center[1], center[1]])
        if self._ycrosshairhandle is None:
            self._ycrosshairhandle = self.axes.axvline(center[0], color='w', ls='--', lw=0.5)
        else:
            self._ycrosshairhandle.set_xdata([center[0], center[0]])
        self._xcrosshairhandle.set_visible(self.showBeamToolButton.isChecked())
        self._ycrosshairhandle.set_visible(self.showBeamToolButton.isChecked())

        # add axis labels
        if self.axesComboBox.currentText() == 'abs. pixel':
            self.axes.set_xlabel('Pixel coordinate')
            self.axes.set_ylabel('Pixel coordinate')
        elif self.axesComboBox.currentText() == 'rel. pixel':
            self.axes.set_xlabel('Distance from the center (pixel)')
            self.axes.set_ylabel('Distance from the center (pixel)')
        elif self.axesComboBox.currentText() == 'detector radius':
            self.axes.set_xlabel('Distance from the center (mm)')
            self.axes.set_ylabel('Distance from the center (mm)')
        elif self.axesComboBox.currentText() == 'twotheta':
            self.axes.set_xlabel(r'Scattering angle $2\theta$ ($^\circ$)')
            self.axes.set_ylabel(r'Scattering angle $2\theta$ ($^\circ$)')
        elif self.axesComboBox.currentText() == 'q':
            self.axes.set_xlabel('$q$ (nm$^{-1}$)')
            self.axes.set_ylabel('$q$ (nm$^{-1}$)')
        else:
            assert False
        if keepzoom:
            self.axes.axis(axlimits)
        self.axes.set_title(self.title)
        self.canvas.draw()

    def setExposure(self, exposure: Exposure, keepzoom: Optional[bool] = None, title: Optional[str] = None):
        self.matrix = exposure.intensity if exposure is not None else None
        self.mask = (exposure.mask == 0) if exposure is not None else None
        self.wavelength = float(exposure.header.wavelength[0]) if exposure is not None else None
        self.pixelsize = float(exposure.header.pixelsize[0]) if exposure is not None else None
        self.beamx = float(exposure.header.beamposcol[0]) if exposure is not None else None
        self.beamy = float(exposure.header.beamposrow[0]) if exposure is not None else None
        self.distance = float(exposure.header.distance[0]) if exposure is not None else None
        self.title = title
        self.replot(keepzoom)

    def setPixelOnly(self, pixelonly: bool):
        self.axesComboBox.setEnabled(not pixelonly)
        self.axesComboBox.setVisible(not pixelonly)
        self.axesComboBox.setCurrentIndex(0)

    def setMask(self, mask: np.ndarray):
        if not mask.shape == self.mask.shape:
            raise ValueError('Mask shape mismatch')
        logger.debug('Updating mask')
        self.mask = mask == 0
        if self._maskhandle is not None:
            self._maskhandle.remove()
            self._maskhandle = None
#        extent, center = self._get_extent()
#        self._maskhandle.set_data(mask)
#        self._maskhandle.set_extent(extent)
#        self._maskhandle.changed()
#        self.canvas.draw_idle()
        self.replot(keepzoom=True)

    def getNormalization(self):
        if self.matrix is None:
            vmin=0.0
            vmax=1.0
        vmin = np.nanmin(self.matrix, initial=np.nan)
        vmax = np.nanmax(self.matrix, initial=np.nan)
        vminpos = np.nanmin(self.matrix[self.matrix>0], initial=np.nan)
        if not np.isfinite(vmin) or not np.isfinite(vmax):
            vmin = 0.0
            vmax = 1.0
        if vmin == vmax:
            vmin = vmin-0.5
            vmax = vmax+0.5
        if not np.isfinite(vminpos):
            vminpos=sys.float_info.epsilon
        if vmax < vminpos:
            vmax = vminpos+0.5
        logger.debug(f'Color scaling limits: {vmin=}, {vmax=}, {vminpos=}')
        if self.colourScaleComboBox.currentText() == 'linear':
            return matplotlib.colors.Normalize(vmin, vmax)
        elif self.colourScaleComboBox.currentText() == 'log10':
            return matplotlib.colors.LogNorm(vminpos, vmax)
        elif self.colourScaleComboBox.currentText() == 'square':
            return matplotlib.colors.PowerNorm(2, vminpos, vmax)
        elif self.colourScaleComboBox.currentText() == 'sqrt':
            return matplotlib.colors.PowerNorm(0.5, vminpos, vmax)
        else:
            assert False

    def colorMapName(self) -> str:
        return self.paletteComboBox.currentText()