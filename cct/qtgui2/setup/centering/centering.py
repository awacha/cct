from typing import Optional

import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSlot as Slot
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure

from .centering_ui import Ui_Form
from ...utils.fsnselector import FSNSelector
from ...utils.h5selector import H5Selector
from ...utils.plotcurve import PlotCurve
from ...utils.plotimage import PlotImage
from ...utils.window import WindowRequiresDevices
from ....core2.algorithms.polar2d import polar2D_pixel
from ....core2.dataclasses.exposure import Exposure


class CenteringUI(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    plotimage: PlotImage
    plotcurve: PlotCurve
    fsnselector: FSNSelector
    h5selector: H5Selector
    exposure: Optional[Exposure] = None
    polarfigure: Figure
    polaraxes: Axes
    polarcanvas: FigureCanvasQTAgg
    polarfigtoolbar: NavigationToolbar2QT

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.fsnselector = FSNSelector(self.fsnSelectorPage)
        self.h5selector = H5Selector(self.hdf5SelectorPage)
        for selector, selectorpage in [(self.fsnselector, self.fsnSelectorPage),
                                       (self.h5selector, self.hdf5SelectorPage)]:
            layout = QtWidgets.QHBoxLayout()
            selectorpage.setLayout(layout)
            layout.addWidget(selector, stretch=1)
            selector.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Preferred)
        self.fsnselector.fsnSelected.connect(self.onFSNSelected)
        self.h5selector.datasetSelected.connect(self.onH5Selected)
        self.fileSequencePagePushButton.toggled.connect(self.onFileSequencePagePushButtonClicked)
        self.hdf5PagePushButton.toggled.connect(self.onH5PagePushButtonClicked)
        self.plotimage = PlotImage(self)
        self.patternVerticalLayout.addWidget(self.plotimage, stretch=1)
        self.plotimage.figure.set_size_inches(1, 0.75)
        self.plotimage.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self.plotcurve = PlotCurve(self)
        self.plotcurve.figure.set_size_inches(1, 0.75)
        self.plotcurve.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self.curveVerticalLayout.addWidget(self.plotcurve, stretch=1)
        self.polarfigure = Figure(figsize=(1, 0.75), constrained_layout=True)
        self.polaraxes = self.polarfigure.add_subplot(1, 1, 1)
        self.polarcanvas = FigureCanvasQTAgg(self.polarfigure)
        self.polarcanvas.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self.polarfigtoolbar = NavigationToolbar2QT(self.polarcanvas, self)
        self.polarVerticalLayout.addWidget(self.polarfigtoolbar)
        self.polarVerticalLayout.addWidget(self.polarcanvas, stretch=1)

    @Slot(bool, name='onFileSequencePagePushButtonClicked')
    def onFileSequencePagePushButtonClicked(self, checked: bool):
        if checked:
            self.fileSelectorStackedWidget.setCurrentWidget(self.fsnSelectorPage)

    @Slot(bool, name='onH5PagePushButtonClicked')
    def onH5PagePushButtonClicked(self, checked: bool):
        if checked:
            self.fileSelectorStackedWidget.setCurrentWidget(self.hdf5SelectorPage)

    @Slot(str, int, name='onFSNSelected')
    def onFSNSelected(self, prefix: str, fsn: int):
        exposure = self.fsnselector.loadExposure()
        self.setExposure(exposure)

    @Slot(str, str, str, name='onH5Selected')
    def onH5Selected(self, h5file: str, sample: str, distkey: str):
        exposure = self.h5selector.loadExposure()
        self.setExposure(exposure)

    def setExposure(self, exposure: Exposure):
        self.exposure = exposure
        self.plotimage.setExposure(exposure)
        self.drawpolar()
        self.drawcurve()

    def drawcurve(self):
        self.plotcurve.clear()
        self.plotcurve.addCurve(self.exposure.radial_average())

    def drawpolar(self):
        self.polaraxes.clear()
        pixmin, pixmax = self.exposure.validpixelrange()
        pix = np.arange(pixmin, pixmax + 1)
        polar = polar2D_pixel(
            self.exposure.intensity, self.exposure.header.beamposrow[0], self.exposure.header.beamposcol[0],
            pix, np.linspace(0, 2 * np.pi, 360))
        self.polaraxes.imshow(
            polar, cmap=self.plotimage.colorMapName(), norm=self.plotimage.getNormalization(),
            extent=(pixmin, pixmax, 0, 360), origin='lower')
        self.polaraxes.axis('auto')
        self.polaraxes.set_xlabel('Distance from origin (pixels)')
        self.polaraxes.set_ylabel('Azimuth angle (°)')
        self.polarcanvas.draw_idle()
