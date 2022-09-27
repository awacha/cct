import logging
from typing import Optional, Tuple, Union, Dict

import lmfit.minimizer
import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSlot as Slot
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure

from .centering_ui import Ui_Form
from .methods.centeringmethod import CenteringMethod
from ...utils.blocksignalscontextmanager import SignalsBlocked
from ...utils.fsnselector import FSNSelector
from ...utils.h5selector import H5Selector
from ...utils.plotcurve import PlotCurve
from ...utils.plotimage import PlotImage
from ...utils.window import WindowRequiresDevices
from ....core2.algorithms.polar2d import polar2D_pixel
from ....core2.dataclasses.exposure import Exposure

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    centeringmethods: Dict[str, CenteringMethod]
    sensitivityfigure: Figure
    sensitivityaxes: Axes
    sensitivityfigtoolbar: NavigationToolbar2QT
    sensitivitycanvas: FigureCanvasQTAgg

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.fsnselector = FSNSelector(self.fsnSelectorPage, horizontal=False)
        self.h5selector = H5Selector(self.hdf5SelectorPage, horizontal=False)
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
        self.patternVerticalLayout = QtWidgets.QVBoxLayout()
        self.patternTab.setLayout(self.patternVerticalLayout)
        self.patternVerticalLayout.addWidget(self.plotimage, stretch=1)
        self.plotimage.figure.set_size_inches(1, 0.75)
        self.plotimage.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self.plotcurve = PlotCurve(self)
        self.plotcurve.figure.set_size_inches(1, 0.75)
        self.plotcurve.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self.curveVerticalLayout = QtWidgets.QVBoxLayout()
        self.curveTab.setLayout(self.curveVerticalLayout)
        self.curveVerticalLayout.addWidget(self.plotcurve, stretch=1)
        self.polarfigure = Figure(figsize=(1, 0.75), constrained_layout=True)
        self.polaraxes = self.polarfigure.add_subplot(1, 1, 1)
        self.polarcanvas = FigureCanvasQTAgg(self.polarfigure)
        self.polarcanvas.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self.polarfigtoolbar = NavigationToolbar2QT(self.polarcanvas, self)
        self.polarVerticalLayout = QtWidgets.QVBoxLayout()
        self.polarTab.setLayout(self.polarVerticalLayout)
        self.polarVerticalLayout.addWidget(self.polarfigtoolbar)
        self.polarVerticalLayout.addWidget(self.polarcanvas, stretch=1)
        self.centeringmethods = {}
        self.sensitivityfigure = Figure(figsize=(1, 0.75), constrained_layout=True)
        self.sensitivityaxes = self.sensitivityfigure.add_subplot(1, 1, 1)
        self.sensitivitycanvas = FigureCanvasQTAgg(self.sensitivityfigure)
        self.sensitivityfigtoolbar = NavigationToolbar2QT(self.sensitivitycanvas, self)
        self.sensitivityFigureVerticalLayout.addWidget(self.sensitivityfigtoolbar)
        self.sensitivityFigureVerticalLayout.addWidget(self.sensitivitycanvas, 1)
        for method in sorted(CenteringMethod.allMethods(), key=lambda cls:cls.name):
            self.centeringmethods[method.name] = method(patternaxes=self.plotimage.axes, curveaxes=self.plotcurve.axes,
                                                        polaraxes=self.polaraxes)
            self.parametersStackedWidget.addWidget(self.centeringmethods[method.name])
            self.methodSelectorComboBox.addItem(method.name)

    @Slot(str, name='on_methodSelectorComboBox_currentTextChanged')
    def on_methodSelectorComboBox_currentTextChanged(self, currentText: str):
        for method in self.centeringmethods.values():
            method.cleanupUI()
            try:
                method.positionFound.disconnect(self.onBeamPositionFound)
            except TypeError:
                pass  # disconnecting a not connected signal
        self.drawcurve()
        self.drawpolar()
        self.plotimage.setExposure(self.exposure, keepzoom=True)
        self.currentMethod().prepareUI(self.exposure)
        self.currentMethod().positionFound.connect(self.onBeamPositionFound)

    def currentMethod(self) -> CenteringMethod:
        return self.centeringmethods[self.methodSelectorComboBox.currentText()]

    @Slot(bool, name='on_runToolButton_clicked')
    def execute(self, checked: bool):
        result: lmfit.minimizer.MinimizerResult = self.centeringmethods[self.methodSelectorComboBox.currentText()].run(
            self.exposure)
        params: lmfit.Parameters = result.params
        logger.debug(params.pretty_print())
        logger.debug(lmfit.fit_report(result))
        logger.debug(str(result.covar))
        self.setBeamPosition(
            row=(
                params['beamrow'].value,
                params['beamrow'].stderr if params['beamrow'].stderr is not None else 0.0),
            column=(
                params['beamcol'].value,
                params['beamcol'].stderr if params['beamcol'].stderr is not None else 0.0))


    @Slot(float, name='on_beamColumnUncertaintyDoubleSpinBox_valueChanged')
    @Slot(float, name='on_beamColumnValueDoubleSpinBox_valueChanged')
    @Slot(float, name='on_beamRowUncertaintyDoubleSpinBox_valueChanged')
    @Slot(float, name='on_beamRowValueDoubleSpinBox_valueChanged')
    def onBeamPositionChanged(self, value: float):
        self.setBeamPosition(
            row=(self.beamRowValueDoubleSpinBox.value(), self.beamRowUncertaintyDoubleSpinBox.value()),
            column=(self.beamColumnValueDoubleSpinBox.value(), self.beamColumnUncertaintyDoubleSpinBox.value()))

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
        self.currentMethod().prepareUI(exposure)
        self.setBeamPosition(row=self.exposure.header.beamposrow, column=self.exposure.header.beamposcol)

    @Slot(float, name='on_radavgMinRadiusDoubleSpinBox_valueChanged')
    @Slot(float, name='on_radavgMaxRadiusDoubleSpinBox_valueChanged')
    @Slot(bool, name='on_radavgMinRadiusCheckBox_toggled')
    @Slot(bool, name='on_radavgMinRadiusCheckBox_toggled')
    @Slot(int, name='on_radavgBinCountSpinBox_valueChanged')
    def drawcurve(self, *args):
        self.plotcurve.clear()
        if self.exposure is None:
            self.plotcurve.replot()
            return
        qmin, qmax = self.exposure.validqrange()
        logger.debug(f'qmin: {qmin}, qmax: {qmax}')
        if self.radavgMinRadiusCheckBox.isChecked():
            qmin = self.exposure.pixeltoq(self.radavgMinRadiusDoubleSpinBox.value())
            logger.debug(f'qmin override to {qmin}')
        if self.radavgMaxRadiusCheckBox.isChecked():
            qmax = self.exposure.pixeltoq(self.radavgMaxRadiusDoubleSpinBox.value())
            logger.debug(f'qmax override to {qmax}')
        if self.radavgBinCountSpinBox.value() == 0:
            nbins = int(np.ceil(self.exposure.qtopixel(qmax) - self.exposure.qtopixel(qmin)))
        else:
            nbins = self.radavgBinCountSpinBox.value()
        self.plotcurve.addCurve(self.exposure.radial_average(np.linspace(qmin, qmax, nbins)))
        self.plotcurve.setSymbolsType(True, True)
        self.plotcurve.setShowErrorBars(False)
        self.plotcurve.showLegend(False)
        self.plotcurve.replot()

    def drawpolar(self):
        self.polaraxes.clear()
        if self.exposure is None:
            self.polarcanvas.draw_idle()
            return
        pixmin, pixmax = self.exposure.validpixelrange()
        pix = np.arange(pixmin, pixmax + 1)
        polar = polar2D_pixel(
            self.exposure.intensity, self.exposure.header.beamposrow[0], self.exposure.header.beamposcol[0],
            pix, np.linspace(0, 2 * np.pi, 360))
        self.polaraxes.imshow(
            polar, cmap=self.plotimage.colorMapName(), norm=self.plotimage.getNormalization(),
            extent=(pixmin, pixmax, 0, 360), origin='lower')
        self.polaraxes.axis('auto')
        self.polaraxes.grid(True, which='both')
        self.polaraxes.set_xlabel('Distance from origin (pixels)')
        self.polaraxes.set_ylabel('Azimuth angle (°)')
        self.polarcanvas.draw_idle()

    def beamrow(self) -> Tuple[float, float]:
        return self.exposure.header.beamposrow

    def beamcol(self) -> Tuple[float, float]:
        return self.exposure.header.beamposcol

    def setBeamrow(self, value: float, uncertainty: float = 0.0):
        self.setBeamPosition(row=(value, uncertainty), column=None)

    def setBeamcol(self, value: float, uncertainty: float = 0.0):
        self.setBeamPosition(row=None, column=(value, uncertainty))

    def setBeamPosition(self, row: Union[None, Tuple[float, float], float],
                        column: Union[None, Tuple[float, float], float]):
        if self.exposure is None:
            return
        if (not isinstance(row, tuple)) and (row is not None):
            row = (row, 0.0)
        if (not isinstance(column, tuple)) and (column is not None):
            column = (column, 0.0)
        if row is not None:
            self.exposure.header.beamposrow = row
        if column is not None:
            self.exposure.header.beamposcol = column
        with SignalsBlocked(self.beamRowValueDoubleSpinBox, self.beamRowUncertaintyDoubleSpinBox,
                            self.beamColumnValueDoubleSpinBox, self.beamColumnUncertaintyDoubleSpinBox):
            if row is not None:
                self.beamRowValueDoubleSpinBox.setValue(row[0])
                self.beamRowUncertaintyDoubleSpinBox.setValue(row[1])
            if column is not None:
                self.beamColumnValueDoubleSpinBox.setValue(column[0])
                self.beamColumnUncertaintyDoubleSpinBox.setValue(column[1])
        self.plotimage.setExposure(self.exposure, keepzoom=True)
        self.drawpolar()
        self.drawcurve()
        self.drawsensitivity()

    def drawsensitivity(self):
        self.sensitivityaxes.clear()
        if self.exposure is None:
            self.sensitivitycanvas.draw_idle()
            return
        bcvalues = np.linspace(
            self.beamcol()[0] - self.sensitivityColumnHalfWidthDoubleSpinBox.value(),
            self.beamcol()[0] + self.sensitivityColumnHalfWidthDoubleSpinBox.value(),
            self.sensitivityColumnCountSpinBox.value()
        )
        brvalues = np.linspace(
            self.beamrow()[0] - self.sensitivityRowHalfWidthDoubleSpinBox.value(),
            self.beamrow()[0] + self.sensitivityRowHalfWidthDoubleSpinBox.value(),
            self.sensitivityRowCountSpinBox.value()
        )
        rowdep = self.currentMethod().goodnessfunction(brvalues, np.ones_like(brvalues) * self.beamcol()[0], self.exposure)
        coldep = self.currentMethod().goodnessfunction(np.ones_like(bcvalues)* self.beamrow()[0], bcvalues, self.exposure)
        self.sensitivityaxes.plot(bcvalues - self.beamcol()[0], coldep, 'bo-', label='X position varied')
        self.sensitivityaxes.plot(brvalues - self.beamrow()[0], rowdep, 'rs-', label='Y position varied')
        self.sensitivityaxes.grid(True, which='both')
        self.sensitivityaxes.set_xlabel('Relative distacne from beam position (pixel)')
        self.sensitivityaxes.set_ylabel(f'Goodness of fit with algorithm "{self.currentMethod().name}"')
        self.sensitivityaxes.legend(loc='best')
        self.sensitivitycanvas.draw_idle()

    @Slot(float, float, float, float, name='onBeamPositionFound')
    def onBeamPositionFound(self, beamrow: float, dbeamrow: float, beamcol: float, dbeamcol: float):
        self.setBeamPosition((beamrow, dbeamrow), (beamcol, dbeamcol))