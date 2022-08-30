import logging
from typing import List, Tuple, Optional

import numpy as np
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import pyqtSlot as Slot

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.axes import Axes
from matplotlib.patches import Circle, Polygon
from matplotlib.widgets import SpanSelector
from matplotlib.lines import Line2D

from .slicesmodel import SectorInformation, SectorModel
from .anisotropy_ui import Ui_Form
from ..fsnselector import FSNSelector
from ..h5selector import H5Selector
from ..plotimage import PlotImage
from ..window import WindowRequiresDevices
from ....core2.algorithms.radavg import maskforannulus, maskforsectors
from ....core2.dataclasses import Exposure

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AnisotropyEvaluator(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    plotimage: PlotImage
    sectorModel: SectorModel

    fig_full: Figure
    figtoolbar_full: NavigationToolbar2QT
    canvas_full: FigureCanvasQTAgg
    axes_full: Axes

    fig_azim: Figure
    figtoolbar_azim: NavigationToolbar2QT
    canvas_azim: FigureCanvasQTAgg
    axes_azim: Axes

    fig_slice: Figure
    figtoolbar_slice: NavigationToolbar2QT
    canvas_slice: FigureCanvasQTAgg
    axes_slice: Axes

    selectorGrid: QtWidgets.QGridLayout
    fsnSelector: FSNSelector
    fsnSelectorLabel: QtWidgets.QLabel
    h5Selector: H5Selector
    h5SelectorLabel: QtWidgets.QLabel
    fullSpanSelector: SpanSelector
    azimSpanSelector: SpanSelector
    exposure: Exposure

    _qrangecircles: Tuple[Optional[Circle], Optional[Circle]]
    _slicelines: List[Line2D]
    _slicearcs: List[Polygon]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._qrangecircles = (None, None)
        self._slicelines = []
        self._slicearcs = []
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.setWindowTitle('Anisotropy Evaluator [*]')
        self.plotimage = PlotImage(self)
        self.patternVerticalLayout.addWidget(self.plotimage)
        self.plotimage.figure.clf()
        self.plotimage.axes.set_facecolor('black')
        self.plotimage.axes.set_title('2D scattering pattern')
        self.plotimage.axesComboBox.setCurrentIndex(self.plotimage.axesComboBox.findText('q'))

        for graphname, vbox in [('full', self.radialVerticalLayout), ('azim', self.azimuthalVerticalLayout),
                                ('slice', self.sliceVerticalLayout)]:
            setattr(self, f'fig_{graphname}', Figure(constrained_layout=True))
            setattr(self, f'canvas_{graphname}', FigureCanvasQTAgg(getattr(self, f'fig_{graphname}')))
            setattr(self, f'figtoolbar_{graphname}', NavigationToolbar2QT(getattr(self, f'canvas_{graphname}'), self))
            getattr(self, f'canvas_{graphname}').setSizePolicy(
                QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
            vbox.addWidget(getattr(self, f'figtoolbar_{graphname}'), stretch=0)
            vbox.addWidget(getattr(self, f'canvas_{graphname}'), stretch=1)
        vboxLayout: QtWidgets.QVBoxLayout = self.layout()
        self.selectorGrid = QtWidgets.QGridLayout()
        vboxLayout.insertLayout(0, self.selectorGrid, stretch=0)
        if self.instrument is not None:
            self.fsnSelector = FSNSelector(self)
            self.fsnSelector.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Preferred)
            self.fsnSelectorLabel = QtWidgets.QLabel("Select by file sequence:", self)
            self.selectorGrid.addWidget(self.fsnSelectorLabel, 0, 0, 1, 1)
            self.selectorGrid.addWidget(self.fsnSelector, 0, 1, 1, 1)
            self.fsnSelector.fsnSelected.connect(self.onFSNSelected)
        else:
            self.fsnSelector = None
        self.h5Selector = H5Selector(self)
        self.h5SelectorLabel = QtWidgets.QLabel("Select from a h5 file:", self)
        self.h5Selector.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Preferred)
        self.selectorGrid.addWidget(self.h5SelectorLabel, 1, 0, 1, 1)
        self.selectorGrid.addWidget(self.h5Selector, 1, 1, 1, 1, QtCore.Qt.AlignLeft)
        self.selectorGrid.setColumnStretch(1, 1)
        self.h5Selector.datasetSelected.connect(self.onH5Selected)
        self.sectorModel = SectorModel()
        self.slicesTreeView.setModel(self.sectorModel)
        self.sectorModel.dataChanged.connect(self.onSectorsChanged)
        self.sectorModel.rowsRemoved.connect(self.onSectorsChanged)
        self.sectorModel.rowsInserted.connect(self.onSectorsChanged)
        self.sectorModel.modelReset.connect(self.onSectorsChanged)

    def enableH5Selector(self, enable: bool = True):
        self.h5Selector.setEnabled(enable)
        self.h5SelectorLabel.setEnabled(enable)
        self.h5Selector.setVisible(enable)
        self.h5SelectorLabel.setVisible(enable)

    def enableFSNSelector(self, enable: bool = True):
        if self.fsnSelector is not None:
            self.fsnSelector.setEnabled(enable)
            self.fsnSelectorLabel.setEnabled(enable)
            self.fsnSelector.setVisible(enable)
            self.fsnSelectorLabel.setVisible(enable)

    @Slot(str, int)
    def onFSNSelected(self, prefix: str, fsn: int):
        self.setExposure(self.fsnSelector.loadExposure())

    @Slot(str, str, str)
    def onH5Selected(self, filename: str, sample: str, distancekey: str):
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
        self.canvas_azim.draw_idle()
        self.canvas_full.draw_idle()
        self.canvas_slice.draw_idle()
        self.sectorModel.clear()

    def removeCircles(self):
        for c in self._qrangecircles:
            try:
                c.remove()
            except ValueError:
                pass
        self._qrangecircles = (None, None)

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
        self._qrangecircles = (
            Circle((0, 0), radius=qmin, color='white', fill=False, linestyle='--', zorder=100),
            Circle((0, 0), radius=qmax, color='white', fill=False, linestyle='--', zorder=100)
        )
        self.plotimage.axes.add_patch(self._qrangecircles[0])
        self.plotimage.axes.add_patch(self._qrangecircles[1])
        self.plotimage.canvas.draw()
        ex = self.exposure
        # ex.mask_nonfinite()
        prevmask = ex.mask
        logger.debug(f'{qmin=}, {qmax=}, pixmin={ex.qtopixel(qmin)}, pixmax={ex.qtopixel(qmax)}')
        try:
            ex.mask = maskforannulus(mask=ex.mask, center_row=ex.header.beamposrow[0],
                                     center_col=ex.header.beamposcol[0], pixmin=ex.qtopixel(qmin),
                                     pixmax=ex.qtopixel(qmax))
            azimcurve = ex.azim_average(self.nAzimSpinBox.value()).sanitize()
            logger.debug(f'{ex.mask.sum()=}')
        finally:
            ex.mask = prevmask
        self.axes_azim.clear()
        self.axes_azim.plot(azimcurve.phi * 180.0 / np.pi, azimcurve.intensity, label='Azimuthal curve')
        self.azimSpanSelector = SpanSelector(self.axes_azim, self.onPhiRangeSelected, 'horizontal', span_stays=True)
        self.axes_azim.set_xlabel(r'$\phi$ (°)')
        self.axes_azim.set_ylabel(r'$d\sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
        self.axes_azim.set_title('Azimuthal scattering curve')
        self.canvas_azim.draw_idle()

    def onPhiRangeSelected(self, phimin: float, phimax: float):
        self.sectorModel.insertRow(self.sectorModel.rowCount(QtCore.QModelIndex()), QtCore.QModelIndex())
        self.sectorModel.appendSector(0.5*(phimin+phimax), phimax-phimin, True, None)

    @Slot(QtCore.QModelIndex, QtCore.QModelIndex, object, name='onSectorsChanged')  # dataChanged
    @Slot(QtCore.QModelIndex, int, int, name='onSectorsChanged')  # rowsInserted, rowsRemoved
    @Slot(name='onSectorsChanged')  # modelReset
    def onSectorsChanged(self):
        self.removeSliceLines()
        self.axes_slice.clear()
        ex = self.exposure
        originalmask = ex.mask
        try:
            for si in self.sectorModel:
                ex.mask = maskforsectors(originalmask, ex.header.beamposrow[0], ex.header.beamposcol[0],
                                         si.phi0 * np.pi / 180., si.dphi * np.pi / 180, symmetric=si.symmetric)
                sliced = ex.radial_average().sanitize()
                line2d = self.axes_slice.loglog(
                    sliced.q, sliced.intensity,
                    label=rf'$\phi_0={si.phi0:.2f}^\circ$, $\Delta\phi = {si.dphi:.2f}^\circ$', color=si.color.name(QtGui.QColor.HexRgb))[0]
                self._slicelines.append(line2d)
                qmax = np.nanmax(ex.q()[0])
                ax = self.plotimage.axes.axis()
                points = np.zeros((101, 2), np.double)
                points[0, :] = 0
                phi = np.linspace(si.phi0 - si.dphi, si.phi0 + si.dphi, 100) * np.pi / 180.
                points[1:101, 0] = qmax * np.cos(phi)
                points[1:101, 1] = - qmax * np.sin(phi)
                self._slicearcs.append(
                    Polygon(points, closed=True, color=line2d.get_color(), zorder=100, alpha=0.5, linewidth=1,
                            fill=True)
                )
                if si.symmetric:
                    self._slicearcs.append(
                        Polygon(-points, closed=True, color=line2d.get_color(), zorder=100, alpha=0.5, linewidth=1,
                            fill=True))
        finally:
            ex.mask = originalmask
        self.axes_slice.legend(loc='best')
        self.axes_slice.set_title('Slices')
        for patch in self._slicearcs:
            self.plotimage.axes.add_patch(patch)
