"""Two-dimensional image plot"""
import logging
import math
from typing import Tuple, Optional

import matplotlib.cm
import numpy as np
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.colorbar import Colorbar
from matplotlib.colors import Normalize, LogNorm
from matplotlib.figure import Figure
from matplotlib.image import AxesImage
from matplotlib.lines import Line2D
from sastool.classes2 import Exposure

from .twodim_ui import Ui_Form
from ..config import Config
from ..project import Project

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ImageView(QtWidgets.QWidget, Ui_Form):
    figure: Figure
    canvas: FigureCanvasQTAgg
    navigationToolbar: NavigationToolbar2QT
    axes: Axes
    config: Config
    project: Project
    _exposure: Exposure = None
    mplimage: AxesImage = None
    mplcrosshair: Tuple[Line2D, Line2D] = None
    mplmask: AxesImage = None
    mplcolorbar: Optional[Colorbar] = None

    def __init__(self, parent, project: Project, config: Config):
        super().__init__(parent)
        self.project = project
        self.config = config
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(figsize=(6, 6), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.navigationToolbar = NavigationToolbar2QT(self.canvas, self)
        self.figureVerticalLayout.addWidget(self.navigationToolbar)
        self.figureVerticalLayout.addWidget(self.canvas)
        self.paletteComboBox.addItems(sorted(matplotlib.cm.cmap_d))
        self.fromConfig()
        self.paletteComboBox.currentIndexChanged.connect(self.onPaletteChanged)
        self.axisScaleComboBox.currentIndexChanged.connect(self.onAxisScaleChanged)
        self.showMaskToolButton.toggled.connect(self.onMaskToggled)
        self.showCenterToolButton.toggled.connect(self.onCenterToggled)
        self.showColorBarToolButton.toggled.connect(self.onColorBarToggled)

    def onPaletteChanged(self):
        logger.debug('Palette changed')
        self.toConfig()
        self._draw()

    def onAxisScaleChanged(self):
        logger.debug('Axis scale changed')
        self.toConfig()
        self._draw()

    def onMaskToggled(self):
        self.toConfig()
        if self.mplmask is not None:
            self.mplmask.set_visible(self.showMaskToolButton.isChecked())
            self.canvas.draw_idle()

    def onCenterToggled(self):
        self.toConfig()
        if self.mplcrosshair is not None:
            for line in self.mplcrosshair:
                line.set_visible(self.showCenterToolButton.isChecked())
            self.canvas.draw_idle()

    def onColorBarToggled(self):
        self.toConfig()
        if self.showColorBarToolButton.isChecked() and self.mplcolorbar is None:
            if self.mplimage is not None:
                self.mplcolorbar = self.figure.colorbar(self.mplimage, ax=self.axes)
        elif (not self.showColorBarToolButton.isChecked()) and (self.mplcolorbar is not None):
            self.mplcolorbar.remove()
            self.mplcolorbar = None
        self.canvas.draw_idle()

    def fromConfig(self):
        self.paletteComboBox.setCurrentIndex(self.paletteComboBox.findText(self.config.colorpalette))
        self.axisScaleComboBox.setCurrentIndex(self.axisScaleComboBox.findText(self.config.twodimaxisvalues))
        self.showMaskToolButton.setChecked(self.config.showmask)
        self.showCenterToolButton.setChecked(self.config.showcenter)
        self.showColorBarToolButton.setChecked(self.config.showcolorbar)

    def toConfig(self):
        self.config.showmask = self.showMaskToolButton.isChecked()
        self.config.showcenter = self.showCenterToolButton.isChecked()
        self.config.showcolorbar = self.showColorBarToolButton.isChecked()
        self.config.colorpalette = self.paletteComboBox.currentText()
        self.config.twodimaxisvalues = self.axisScaleComboBox.currentText()

    def setExposure(self, exposure: Exposure):
        self._exposure = exposure
        self.setWindowTitle(str(exposure))
        self._draw()

    def exposure(self) -> Exposure:
        return self._exposure

    def _draw(self):
        self.figure.clear()
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.axes.set_facecolor('black')
        if self._exposure is None:
            return
        # left, right, bottom, top: the data coordinates of the rectangle in which the matrix will be painted.
        extent = (-0.5, self.exposure().shape[1] - 0.5, self.exposure().shape[0] - 0.5, -0.5)
        if self.axisScaleComboBox.currentText() == 'pixel':
            # keep the previously defined extent coordinates
            self.axes.set_xlabel('Pixel')
            self.axes.set_ylabel('Pixel')
            center = (float(self._exposure.header.beamcenterx), float(self._exposure.header.beamcentery))
        elif self.axisScaleComboBox.currentText() == 'radius':
            extent = ((extent[0] - self._exposure.header.beamcenterx) * self._exposure.header.pixelsizex,
                      (extent[1] - self._exposure.header.beamcenterx) * self._exposure.header.pixelsizex,
                      (extent[2] - self._exposure.header.beamcentery) * self._exposure.header.pixelsizey,
                      (extent[3] - self._exposure.header.beamcentery) * self._exposure.header.pixelsizey,
                      )
            self.axes.set_xlabel('Detector radius (mm)')
            self.axes.set_ylabel('Detector radius (mm)')
            center = (0, 0)
        elif self.axisScaleComboBox.currentText() == 'q':
            extent = ((extent[0] - self._exposure.header.beamcenterx) * self._exposure.header.pixelsizex,
                      (extent[1] - self._exposure.header.beamcenterx) * self._exposure.header.pixelsizex,
                      (extent[2] - self._exposure.header.beamcentery) * self._exposure.header.pixelsizey,
                      (extent[3] - self._exposure.header.beamcentery) * self._exposure.header.pixelsizey,
                      )
            extent = tuple([math.sin(
                math.atan2(r, self._exposure.header.distance) * 0.5) * 4 * math.pi / self._exposure.header.wavelength
                            for r in extent])
            self.axes.set_xlabel('$q$ (nm$^{-1}$)')
            self.axes.set_ylabel('$q$ (nm$^{-1}$)')
            center = (0, 0)
        else:
            raise ValueError('Unknown axis scaling type: {}'.format(self.axisScaleComboBox.currentText()))
        extent = tuple([float(x) for x in extent])
        # draw the image
        logger.debug('Drawing the image.')
        logger.debug('Extent: {}'.format(extent))
        self.mplimage = self.axes.imshow(
            self._exposure.intensity,
            cmap=self.paletteComboBox.currentText(),
            norm=LogNorm(),
            aspect='equal',
            interpolation='nearest',
            alpha=1,
            vmin=None, vmax=None,
            origin='upper',
            extent=extent,
        )
        # create an image for the mask matrix
        maskmat = self._exposure.mask.astype(np.float)
        maskmat[maskmat != 0] = np.nan
        self.mplmask = self.axes.imshow(
            maskmat,
            cmap='gray_r',
            norm=Normalize(),
            aspect='equal',
            interpolation='nearest',
            alpha=0.7,
            vmin=None, vmax=None, origin='upper',
            extent=extent
        )
        self.mplmask.set_visible(self.showMaskToolButton.isChecked())

        self.mplcrosshair = (
            self.axes.axvline(center[0], color='white'),
            self.axes.axhline(center[1], color='white')
        )
        for line in self.mplcrosshair:
            line.set_visible(self.showCenterToolButton.isChecked())
        if self.showColorBarToolButton.isChecked():
            self.mplcolorbar = self.figure.colorbar(self.mplimage, ax=self.axes)
        else:
            self.mplcolorbar = None
        self.canvas.draw_idle()
        self.navigationToolbar.update()
        # ToDo: draw logo as well.
