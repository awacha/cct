import datetime
import gc

import matplotlib.cm
import matplotlib.colors
import numpy as np
import sastool.io.credo_cct
import scipy.misc
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from sastool.classes2 import Exposure

from .plotimage_ui import Ui_Form


def get_colormaps():
    return sorted(
        [cm for cm in dir(matplotlib.cm) if isinstance(getattr(matplotlib.cm, cm), matplotlib.colors.Colormap)],
        key=lambda x: x.lower())


class PlotImage(QtWidgets.QWidget, Ui_Form):
    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self._exposure = None
        self.setupUi(self)

    def _testimage(self):
        header = sastool.io.credo_cct.Header(
            {'accounting':
                 {'operator': 'Anonymous',
                  'projectid': 'Dummy project',
                  },
             'sample':
                 {'title': 'Test image',
                  'transmission.val': 0.5,
                  'transmission.err': 0.01,
                  'thickness.val': 0.1,
                  'thickness.err': 0.001,
                  'distminus.val': 0,
                  'distminus.err': 0,
                  'positionx.val': 0,
                  'positiony.val': 0,
                  'positionx.err': 0,
                  'positiony.err': 0,
                  },
             'motors':
                 {'dummy_motor': 0,
                  },
             'exposure':
                 {'fsn': 0,
                  'exptime': 100,
                  'startdate': str(datetime.datetime.now()),
                  },
             'geometry':
                 {'wavelength': 0.15418,
                  'wavelength.err': 0.001,
                  'truedistance': 100,
                  'truedistance.err': 0.05,
                  'beamposy': 200,
                  'beamposy.err': 0.5,
                  'beamposx': 100,
                  'beamposx.err': 0.5,
                  'pixelsize': 0.172,
                  'mask': 'mask.mat',
                  },
             'environment':
                 {'temperature': 20,
                  'vacuum_pressure': 1e-5,
                  },
             'datareduction':
                 {'flux': 10,
                  'flux.err': 0.1,
                  'emptybeamFSN': 0,
                  'absintrefFSN': 0,
                  'absintfactor': 1,
                  'absintfactor.err': 0,
                  }
             })
        m = scipy.misc.face(True)
        self._exposure = sastool.io.credo_cct.Exposure(m * 1.0,
                                  m * 0.1,
                                  header,
                                  m - m.min() > 0.2 * (m.max() - m.min()))
        self.replot()

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.colourScaleComboBox.addItems(['linear', 'logarithmic', 'square', 'square root'])
        self.colourScaleComboBox.setCurrentIndex(self.colourScaleComboBox.findText('logarithmic'))
        self.paletteComboBox.addItems(get_colormaps())
        self.paletteComboBox.setCurrentIndex(self.paletteComboBox.findText(matplotlib.rcParams['image.cmap']))
        self.axesComboBox.addItems(['abs. pixel', 'rel. pixel', 'detector radius', 'twotheta', 'q'])
        self.axesComboBox.setCurrentIndex(self.axesComboBox.findText('q'))
        layout = QtWidgets.QVBoxLayout(self.figureContainer)
        self.figure = Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(1, 1, 1)
        assert isinstance(self.axes, Axes)
        self.axes.set_facecolor('black')
        layout.addWidget(self.canvas)
        self.figtoolbar = NavigationToolbar2QT(self.canvas, self.figureContainer)
        layout.addWidget(self.figtoolbar)
        assert isinstance(self.figtoolbar, QtWidgets.QToolBar)
        self.showToolbarButton=QtWidgets.QToolButton(self.figtoolbar)
        self.showToolbarButton.setText('Plot setup')
        self.showToolbarButton.setCheckable(True)
        self.showToolbarButton.setChecked(False)
        self.toolbar.setVisible(False)
        self.showToolbarButton.toggled.connect(self.toolbarVisibility)
        self.figtoolbar.insertWidget(self.figtoolbar.actions()[-1], self.showToolbarButton).setVisible(True)
        self.colourScaleComboBox.currentIndexChanged.connect(self.colourScaleChanged)
        self.axesComboBox.currentIndexChanged.connect(self.axesTypeChanged)
        self.paletteComboBox.currentIndexChanged.connect(self.paletteChanged)
        self.showColourBarPushButton.toggled.connect(self.showColourBarChanged)
        self.showMaskPushButton.toggled.connect(self.showMaskChanged)
        self.showBeamPushButton.toggled.connect(self.showBeamChanged)
        self._testimage()
        self.figtoolbar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def toolbarVisibility(self, state):
        self.toolbar.setVisible(state)

    def showColourBarChanged(self, checked):
        self.replot_colourbar()
        self.canvas.draw()

    def showMaskChanged(self, checked):
        self.replot_mask()
        self.canvas.draw()

    def showBeamChanged(self, checked):
        self.replot_crosshair()
        self.canvas.draw()

    def colourScaleChanged(self):
        self.replot()

    def paletteChanged(self):
        self.replot()

    def axesTypeChanged(self):
        self.replot()

    def replot_colourbar(self):
        if hasattr(self, '_colorbar'):
            self._colorbar.remove()
            del self._colorbar
        if self.showColourBarPushButton.isChecked():
            self._colorbar = self.figure.colorbar(self._image, ax=self.axes, use_gridspec=True)

    def replot_mask(self):
        if hasattr(self, '_mask'):
            self._mask.remove()
            del self._mask
        if self.showMaskPushButton.isChecked():
            ex = self.exposure()
            assert isinstance(ex, Exposure)
            mf = np.ones(ex.shape, np.float)
            mf[ex.mask != 0] = np.nan
            self._mask = self.axes.imshow(mf, cmap='gray_r', interpolation='nearest', aspect='equal', alpha=0.7,
                                          origin='upper', extent=self._image.get_extent(), zorder=2)
        gc.collect()

    def replot_crosshair(self):
        if hasattr(self, '_crosshair'):
            for c in self._crosshair:
                c.remove()
            del self._crosshair
        if self.showBeamPushButton.isChecked():
            ex = self.exposure()
            assert isinstance(ex, Exposure)
            axestype = self.axesComboBox.currentText()
            if axestype == 'abs. pixel':
                matrix=self.exposure().intensity
                beampos = (ex.header.beamcenterx.val, ex.header.beamcentery.val)
                assert isinstance(self.axes, Axes)
                self._crosshair=self.axes.plot([0, matrix.shape[1]],[beampos[1],beampos[1]],'w-',
                                                [beampos[0], beampos[0]], [0, matrix.shape[0]], 'w-',
                                               scalex=False, scaley=False)
            else:
                extent=self._image.get_extent()
                self._crosshair=self.axes.plot(extent[0:2], [0,0], 'w-',
                                               [0,0], extent[2:4], 'w-', scalex=False, scaley=False)
        gc.collect()

    def replot(self):
        ex = self.exposure()
        assert isinstance(ex, Exposure)
        assert isinstance(self.axes, Axes)
        if self.colourScaleComboBox.currentText() == 'linear':
            norm = matplotlib.colors.Normalize()
        elif self.colourScaleComboBox.currentText() == 'logarithmic':
            norm = matplotlib.colors.LogNorm()
        elif self.colourScaleComboBox.currentText() == 'square':
            norm = matplotlib.colors.PowerNorm(2)
        elif self.colourScaleComboBox.currentText() == 'square root':
            norm = matplotlib.colors.PowerNorm(0.5)
        else:
            assert False
        matrix = ex.intensity
        if self.colourScaleComboBox.currentText() in ['logarithmic', 'square', 'square root']:
            matrix[matrix <= 0] = np.nan

        beampos = (ex.header.beamcenterx.val, ex.header.beamcentery.val)
        distance = ex.header.distance.val
        wavelength = ex.header.wavelength.val
        pixelsize = ex.header.pixelsizex.val, ex.header.pixelsizey.val
        axesscale = self.axesComboBox.currentText()

        if axesscale == 'abs. pixel':
            extent = (0, matrix.shape[1] - 1, matrix.shape[0] - 1, 0)  # left, right, bottom, top
        elif axesscale == 'rel. pixel':
            extent = (0 - beampos[0], matrix.shape[1] - 1 - beampos[0],
                      matrix.shape[0] - 1 - beampos[1], 0 - beampos[1], )
        elif axesscale == 'detector radius':
            extent = (
                (0 - beampos[0]) * pixelsize[0],
                (matrix.shape[1] - 1 - beampos[0]) * pixelsize[0],
                (matrix.shape[0] - 1 - beampos[1]) * pixelsize[1],
                (0 - beampos[1]) * pixelsize[1],
            )
        elif axesscale == 'twotheta':
            extent = (np.arctan((0 - beampos[0]) * pixelsize[0] / distance) * 180 / np.pi,
                      np.arctan((matrix.shape[1] - 1 - beampos[
                          0]) * pixelsize[0] / distance) * 180 / np.pi,
                      np.arctan((matrix.shape[0] - 1 - beampos[1]) *
                                pixelsize[1] / distance) * 180 / np.pi,
                      np.arctan((0 - beampos[1]) * pixelsize[1] / distance) * 180 / np.pi,
                      )
        elif axesscale == 'q':
            extent = (4 * np.pi * np.sin(
                0.5 * np.arctan((0 - beampos[0]) * pixelsize[0] / distance)) / wavelength,
                      4 * np.pi * np.sin(0.5 * np.arctan((matrix.shape[1] - 1 - beampos[
                          0]) * pixelsize[0] / distance)) / wavelength,
                      4 * np.pi * np.sin(0.5 * np.arctan((matrix.shape[0] - 1 - beampos[
                          1]) * pixelsize[1] / distance)) / wavelength,
                      4 * np.pi * np.sin(
                          0.5 * np.arctan(
                              (0 - beampos[1]) * pixelsize[1] / distance)) / wavelength,
                      )
        else:
            raise ValueError(axesscale)

        if hasattr(self, '_image'):
            if hasattr(self, '_colorbar'):
                self._colorbar.remove()
                del self._colorbar
            self._image.remove()
            del self._image
        self._image = self.axes.imshow(matrix,
                                       cmap=self.paletteComboBox.currentText(), norm=norm,
                                       aspect='equal', interpolation='nearest', origin='upper', zorder=1, extent=extent)
        self.replot_colourbar()
        self.replot_crosshair()
        self.replot_mask()
        self._title = self.axes.set_title('#{:d}: {} ({:.2f} mm)'.format(ex.header.fsn,
                                                                         ex.header.title,
                                                                         ex.header.distance))

        if axesscale == 'abs. pixel':
            self.axes.xaxis.set_label_text('Absolute column coordinate (pixel)')
            self.axes.yaxis.set_label_text('Absolute row coordinate (pixel)')
        elif axesscale == 'rel. pixel':
            self.axes.xaxis.set_label_text('Relative column coordinate (pixel)')
            self.axes.yaxis.set_label_text('Relative row coordinate (pixel)')
        elif axesscale == 'detector radius':
            self.axes.xaxis.set_label_text('Horizontal distance from the beam center (mm)')
            self.axes.yaxis.set_label_text('Vertical distance from the beam center (mm)')
        elif axesscale == 'twotheta':
            self.axes.xaxis.set_label_text('$2\\theta_x$ ($^\circ$)')
            self.axes.yaxis.set_label_text('$2\\theta_y$ ($^\circ$)')
        elif axesscale == 'q':
            self.axes.xaxis.set_label_text('$q_x$ (nm$^{-1}$)')
            self.axes.yaxis.set_label_text('$q_y$ (nm$^{-1}$)')
        else:
            assert False
        self.canvas.draw()
        gc.collect()

    def setExposure(self, exposure: Exposure):
        self._exposure = exposure
        del exposure
        self.replot()

    def exposure(self) -> Exposure:
        return self._exposure

    def setOnlyAbsPixel(self, status=True):
        if status:
            self.axesComboBox.setCurrentIndex(0)
            self.axesComboBox.setEnabled(False)
        else:
            self.axesComboBox.setEnabled(True)