import logging
from typing import Optional

import matplotlib
import matplotlib.cm
import matplotlib.colors
import numpy as np
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.colorbar import Colorbar
from matplotlib.figure import Figure
from matplotlib.image import AxesImage
from matplotlib.lines import Line2D
from sastool.classes2 import Exposure

from .plotimage_ui import Ui_Form

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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

    _cmapaxis: Optional[Colorbar] = None
    _imghandle: Optional[AxesImage] = None
    _maskhandle: Optional[AxesImage] = None
    _xcrosshairhandle: Optional[Line2D] = None
    _ycrosshairhandle: Optional[Line2D] = None

    _normalizationdict = {
        'linear': matplotlib.colors.Normalize(),
        'log10': matplotlib.colors.LogNorm(),
        'square': matplotlib.colors.PowerNorm(2),
        'sqrt': matplotlib.colors.PowerNorm(0.5),
    }

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.mask = None
        self.matrix = None
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(figsize=(6, 4), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figToolbar = NavigationToolbar2QT(self.canvas, self)
        self.layout().addWidget(self.figToolbar)
        self.layout().addWidget(self.canvas, 1)
        self.canvas.mpl_connect('resize_event', self.onCanvasResize)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding)
        gs = self.figure.add_gridspec(1, 1)
        self.axes = self.figure.add_subplot(gs[:, :])
        self.axes.set_facecolor('black')
        self.canvas.draw_idle()
        self.paletteComboBox.addItems(sorted(matplotlib.cm.cmap_d))
        self.paletteComboBox.setCurrentIndex(self.paletteComboBox.findText(matplotlib.rcParams['image.cmap']))
        self.paletteComboBox.currentIndexChanged.connect(self.replot)
        self.colourScaleComboBox.currentIndexChanged.connect(self.replot)
        self.axesComboBox.currentIndexChanged.connect(self.axisScaleChanged)
        self.showColourBarToolButton.toggled.connect(self.showColourBar)
        self.showBeamToolButton.toggled.connect(self.showBeam)
        self.showMaskToolButton.toggled.connect(self.showMask)
        self.equalAspectToolButton.toggled.connect(self.changeAspect)

    def axisScaleChanged(self):
        self.replot()
        (left, right, bottom, top), center = self._get_extent()
        self.axes.axis([left, right, bottom, top])
        self.canvas.draw_idle()
        self.figToolbar.update()

    def showColourBar(self, showit: bool):
        if self._cmapaxis is not None:
            self._cmapaxis.ax.set_visible(showit)
            self.canvas.draw_idle()

    def showMask(self, showit: bool):
        if self._maskhandle is not None:
            self._maskhandle.set_visible(showit)
            self.canvas.draw_idle()

    def showBeam(self, showit: bool):
        if self._xcrosshairhandle is not None:
            self._xcrosshairhandle.set_visible(showit)
            self.canvas.draw_idle()
        if self._ycrosshairhandle is not None:
            self._ycrosshairhandle.set_visible(showit)
            self.canvas.draw_idle()

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

    def replot(self):
        extent, center = self._get_extent()
        # now plot the matrix
        if self._imghandle is None:
            self._imghandle = self.axes.imshow(
                self.matrix,
                cmap=self.paletteComboBox.currentText(),
                norm=self._normalizationdict[self.colourScaleComboBox.currentText()],
                aspect='equal' if self.equalAspectToolButton.isChecked() else 'auto',
                interpolation='nearest',
                alpha=1.0,
                origin='upper',
                extent=extent,
            )
        else:
            self._imghandle.set_data(self.matrix)
            self._imghandle.set_cmap(self.paletteComboBox.currentText())
            self._imghandle.set_norm(self._normalizationdict[self.colourScaleComboBox.currentText()])
            self._imghandle.set_extent(extent)
            self._imghandle.autoscale()
            self._imghandle.changed()
        # color bar
        if self._cmapaxis is None:
            self._cmapaxis = self.figure.colorbar(
                self._imghandle,
                cax=self._cmapaxis.ax if self._cmapaxis is not None else None,
                ax=None if self._cmapaxis is not None else self.axes)
        else:
            logger.debug('Updating cmap')
        self._cmapaxis.ax.set_visible(self.showColourBarToolButton.isChecked())

        # now plot the mask
        logger.debug(f'Mask: {(self.mask != 0).sum()} nonzero, {(self.mask == 0).sum()} zero pixels')
        if self._maskhandle is None:
            self._maskhandle = self.axes.imshow(
                self.mask,
                cmap=maskcmap,
                aspect='equal' if self.equalAspectToolButton.isChecked() else 'auto',
                interpolation='nearest',
                # alpha=0.7,  # no need to specify: the color map does the job.
                origin='upper',
                extent=extent,
            )
        else:
            self._maskhandle.set_data(self.mask)
            self._maskhandle.set_extent(extent)
            self._maskhandle.changed()
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
        self.canvas.draw_idle()

    def setExposure(self, exposure: Exposure):
        self.matrix = exposure.intensity
        self.mask = exposure.mask == 0
        self.wavelength = float(exposure.header.wavelength)
        self.pixelsize = float(exposure.header.pixelsizex)
        self.beamx = float(exposure.header.beamcenterx)
        self.beamy = float(exposure.header.beamcentery)
        self.distance = float(exposure.header.distance)
        self.replot()
