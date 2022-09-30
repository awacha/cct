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
logger.setLevel(logging.INFO)


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
    lastminimizerresult: Optional[lmfit.minimizer.MinimizerResult] = None

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
        for method in sorted(CenteringMethod.allMethods(), key=lambda cls: cls.name):
            self.centeringmethods[method.name] = method(patternaxes=self.plotimage.axes, curveaxes=self.plotcurve.axes,
                                                        polaraxes=self.polaraxes)
            self.parametersStackedWidget.addWidget(self.centeringmethods[method.name])
            self.methodSelectorComboBox.addItem(method.name)

    @Slot(bool, name='on_beamRowSaveToolButton_clicked')
    def on_beamRowSaveToolButton_clicked(self, checked: bool):
        self.instrument.config[('geometry', 'beamposx')] = self.beamrow()[0]
        self.instrument.config[('geometry', 'beamposx.err')] = self.beamrow()[1]
        logger.info(
            f'Updated beam row (vertical) coordinate to {self.instrument.config[("geometry", "beamposx")]:.5f} \xb1 '
            f'{self.instrument.config[("geometry", "beamposx.err")]:.5f} pixel')

    @Slot(bool, name='on_beamColumnSaveToolButton_clicked')
    def on_beamColumnSaveToolButton_clicked(self, checked: bool):
        self.instrument.config[('geometry', 'beamposy')] = self.beamcol()[0]
        self.instrument.config[('geometry', 'beamposy.err')] = self.beamcol()[1]
        logger.info(
            f'Updated beam column (horizontal) coordinate to {self.instrument.config[("geometry", "beamposy")]:.5f} \xb1 '
            f'{self.instrument.config[("geometry", "beamposy.err")]:.5f} pixel')


    @Slot(bool, name='on_sensitivityGoodnessScoreRadioButton_toggled')
    @Slot(bool, name='on_sensitivity1stDerivativeRadioButton_toggled')
    @Slot(bool, name='on_sensitivity2ndDerivativeRadioButton_toggled')
    def sensitivityreplotneeded(self, checked: bool):
        if checked:  # only draw once
            self.drawsensitivity()

    @Slot(bool, name='on_sensitivityRecalculatePushButton_clicked')
    def on_sensitivityRecalculatePushButton_clicked(self, checked: bool):
        self.drawsensitivity()
        self.estimateuncertainty(self.sensitivityRowHalfWidthDoubleSpinBox.value(),
                                 self.sensitivityColumnHalfWidthDoubleSpinBox.value(),
                                 self.sensitivityRowCountSpinBox.value(),
                                 self.sensitivityColumnCountSpinBox.value())


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
        self.lastminimizerresult = result
        params: lmfit.Parameters = result.params
        logger.debug(params.pretty_print())
        logger.debug(lmfit.fit_report(result))
        #        logger.debug(str(result.covar))
        logger.debug(f'{result.status=}, {result.message=}, {result.nfev=}, {result.success=}, {result.errorbars=}, ')
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
        logger.debug(f'onH5Selected({h5file}, {sample}, {distkey})')
        exposure = self.h5selector.loadExposure()
        self.setExposure(exposure)

    def setExposure(self, exposure: Exposure):
        logger.debug('Centering.setExposure()')
        self.exposure = exposure
        logger.debug('Calling currentMethod().prepareUI()')
        self.currentMethod().prepareUI(exposure)
        logger.debug('Calling currentMethod().prepareUI() done.')
        logger.debug('Setting beam position.')
        self.setBeamPosition(row=self.exposure.header.beamposrow, column=self.exposure.header.beamposcol)
        logger.debug('Centering.setExposure() done.')

    @Slot(float, name='on_radavgMinRadiusDoubleSpinBox_valueChanged')
    @Slot(float, name='on_radavgMaxRadiusDoubleSpinBox_valueChanged')
    @Slot(bool, name='on_radavgMinRadiusCheckBox_toggled')
    @Slot(bool, name='on_radavgMinRadiusCheckBox_toggled')
    @Slot(int, name='on_radavgBinCountSpinBox_valueChanged')
    def drawcurve(self, *args):
        logger.debug('Centering.drawcurve()')
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
        logger.debug('Centering.drawcurve() done.')

    def drawpolar(self):
        logger.debug('Centering.drawpolar()')
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
        logger.debug('Centering.drawpolar() done')

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
        #self.drawsensitivity()

    def drawsensitivity(self):
        logger.debug('Centering.drawsensitivity()')

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
        rowdep = np.array(self.currentMethod().goodnessfunction(brvalues, np.ones_like(brvalues) * self.beamcol()[0],
                                                                self.exposure))
        coldep = np.array(self.currentMethod().goodnessfunction(np.ones_like(bcvalues) * self.beamrow()[0], bcvalues,
                                                                self.exposure))
        if np.all(~np.isfinite(rowdep)) or np.all(~np.isfinite(coldep)):
            self.sensitivitycanvas.draw_idle()
            return None
        row = brvalues - self.beamrow()[0]
        col = bcvalues - self.beamcol()[0]

        if self.sensitivityGoodnessScoreRadioButton.isChecked():
            nderiv = 0
            ylabel = f'Goodness score with algorithm "{self.currentMethod().name}"'
        elif self.sensitivity1stDerivativeRadioButton.isChecked():
            nderiv = 1
            ylabel = f'1st derivative of goodness score with algorithm "{self.currentMethod().name}"'
        elif self.sensitivity2ndDerivativeRadioButton.isChecked():
            nderiv = 2
            ylabel = f'2nd derivative of goodness score with algorithm "{self.currentMethod().name}"'
        else:
            assert False

        for i in range(nderiv):
            # differentiate
            rowdep = (rowdep[1:] - rowdep[:-1]) / (row[1:] - row[:-1])
            coldep = (coldep[1:] - coldep[:-1]) / (col[1:] - col[:-1])
            row = 0.5 * (row[1:] + row[:-1])
            col = 0.5 * (col[1:] + col[:-1])

        self.sensitivityaxes.plot(col, coldep, 'bo-', label='X position varied')
        self.sensitivityaxes.plot(row, rowdep, 'rs-', label='Y position varied')
        self.sensitivityaxes.grid(True, which='both')
        self.sensitivityaxes.set_xlabel('Relative distance from beam position (pixel)')
        self.sensitivityaxes.set_ylabel(ylabel)
        self.sensitivityaxes.legend(loc='best')
        self.sensitivitycanvas.draw_idle()
        logger.debug('Centering.drawsensitivity() done')


    @Slot(float, float, float, float, name='onBeamPositionFound')
    def onBeamPositionFound(self, beamrow: float, dbeamrow: float, beamcol: float, dbeamcol: float):
        self.setBeamPosition((beamrow, dbeamrow), (beamcol, dbeamcol))

    def estimateuncertainty(self, rowhalfwidth: float, colhalfwidth: float, rowcount: int, colcount: int):
        row = np.outer(np.linspace(-rowhalfwidth, rowhalfwidth, rowcount), np.ones(colcount))
        col = np.outer(np.ones(rowcount), np.linspace(-colhalfwidth, colhalfwidth, colcount))
        fvalue = self.currentMethod().goodnessfunction(row + self.beamrow()[0], col + self.beamcol()[0], self.exposure)
        if np.any(~np.isfinite(fvalue)):
            return None
        optimum = self.currentMethod().goodnessfunction(self.beamrow()[0], self.beamcol()[0], self.exposure)
        logger.debug(f'{optimum.shape=}')
        fvalue_row = self.currentMethod().goodnessfunction(
            np.array([-rowhalfwidth, rowhalfwidth]) + self.beamrow()[0],
            np.array([0,0]) + self.beamcol()[0], self.exposure)
        fvalue_col = self.currentMethod().goodnessfunction(
            np.array([0,0]) + self.beamrow()[0],
            np.array([-colhalfwidth, colhalfwidth]) + self.beamcol()[0],
            self.exposure
        )
        def modelfunction(deltarow, deltacolumn, H11, H12, H22, const):
            return 0.5 * (
                        H11 * deltarow * deltarow + 2 * H12 * deltarow * deltacolumn + H22 * deltacolumn * deltacolumn) + const

        model = lmfit.Model(modelfunction, independent_vars=['deltarow', 'deltacolumn'])
        params = model.make_params(H11=1.0, H12=0.0, H22=1.0, const=float(optimum))
        params['H11'].value = float((0.5*(fvalue_row[0]+fvalue_row[-1]) - optimum) / rowhalfwidth**2)
        params['H12'].vary = True
        params['H22'].value = float((0.5 * (fvalue_col[0] + fvalue_col[-1]) -optimum)/ colhalfwidth**2)
        result = model.fit(fvalue, deltarow=row, deltacolumn=col, params=params)
        logger.debug(str(result.params))
        logger.debug(lmfit.fit_report(result))
        hessian = np.array([
            [result.params['H11'].value, result.params['H12'].value],
            [result.params['H12'].value, result.params['H22'].value]
        ])
        if self.lastminimizerresult is not None:
            self.lastminimizerresult.cov = 2 * np.linalg.inv(hessian)
            logger.debug(f'Covariance: {self.lastminimizerresult.cov}')
            self.beamRowUncertaintyDoubleSpinBox.setValue(self.lastminimizerresult.cov[0,0]**0.5)
            self.beamColumnUncertaintyDoubleSpinBox.setValue(self.lastminimizerresult.cov[1,1]**0.5)
            logger.debug(f'{self.lastminimizerresult.cov[0,0]**0.5}, {self.lastminimizerresult.cov[1,1]**0.5}')

