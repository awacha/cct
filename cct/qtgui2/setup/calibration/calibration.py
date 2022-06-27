import logging
import re
from typing import Optional, Tuple

import numpy as np
import scipy.odr
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSlot as Slot
from matplotlib.axes import Axes
from matplotlib.backend_bases import PickEvent
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.widgets import Cursor

from .calibration_ui import Ui_MainWindow
from ...utils.fsnselector import FSNSelector
from ...utils.plotcurve import PlotCurve
from ...utils.plotimage import PlotImage
from ...utils.window import WindowRequiresDevices
from ....core2.algorithms.centering import findbeam, centeringalgorithms
from ....core2.algorithms.peakfit import fitpeak, PeakType
from ....core2.dataclasses import Exposure, Curve
from ....core2.instrument.components.calibrants.q import QCalibrant

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Calibration(QtWidgets.QMainWindow, WindowRequiresDevices, Ui_MainWindow):
    fsnSelector: FSNSelector
    plotimage: PlotImage
    plotcurve: PlotCurve
    exposure: Optional[Exposure] = None
    curve: Optional[Curve] = None
    manualcursor: Optional[Cursor] = None
    axes: Axes
    figure: Figure
    figtoolbar: NavigationToolbar2QT
    canvas: FigureCanvasQTAgg
    dist_sample_det: Tuple[float, float] = (0, 0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.fsnSelector = FSNSelector(self.fsnSelectorGroupBox)
        self.fsnSelectorGroupBox.setLayout(QtWidgets.QVBoxLayout())
        self.fsnSelectorGroupBox.layout().addWidget(self.fsnSelector)
        self.fsnSelector.fsnSelected.connect(self.onFSNSelected)
        self.fsnSelector.setPrefix(self.instrument.config['path']['prefixes']['tst'])
        self.tab2D.setLayout(QtWidgets.QVBoxLayout())
        self.plotimage = PlotImage(self.tab2D)
        self.tab2D.layout().addWidget(self.plotimage)
        self.tab1D.setLayout(QtWidgets.QVBoxLayout())
        self.plotcurve = PlotCurve(self.tab1D)
        self.plotcurve.setSymbolsType(True, True)
        self.tab1D.layout().addWidget(self.plotcurve)
        self.centeringMethodComboBox.addItems(sorted(centeringalgorithms))
        self.centeringMethodComboBox.setCurrentIndex(0)
        self.centeringPushButton.clicked.connect(self.findCenter)
        self.manualCenteringPushButton.clicked.connect(self.manualCentering)
        self.plotimage.canvas.mpl_connect('pick_event', self.on2DPick)
        self.plotimage.axes.set_picker(True)
        self.instrument.calibrants.calibrantListChanged.connect(self.populateCalibrants)
        self.populateCalibrants()
        self.calibrantComboBox.currentIndexChanged.connect(self.calibrantChanged)
        self.peakComboBox.currentIndexChanged.connect(self.onCalibrantPeakSelected)
        self.fitGaussPushButton.clicked.connect(self.fitPeak)
        self.fitLorentzPushButton.clicked.connect(self.fitPeak)
        self.addPairToolButton.clicked.connect(self.addPair)
        self.removePairToolButton.clicked.connect(self.removePair)
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(self.figure.add_gridspec(1, 1)[:, :])
        self.figtoolbar = NavigationToolbar2QT(self.canvas, self)
        self.tabDistance.setLayout(QtWidgets.QVBoxLayout())
        self.tabDistance.layout().addWidget(self.figtoolbar)
        self.tabDistance.layout().addWidget(self.canvas)
        self.saveSDDistToolButton.clicked.connect(self.saveParameter)
        self.saveBeamXToolButton.clicked.connect(self.saveParameter)
        self.saveBeamYToolButton.clicked.connect(self.saveParameter)
        self.beamXDoubleSpinBox.valueChanged.connect(self.beamPosUIEdit)
        self.centerOfGravityPushButton.clicked.connect(self.getCentreOfGravity)

        self.canvas.draw_idle()

    @Slot(float)
    def beamPosUIEdit(self, value: float):
        if self.exposure is None:
            return
        beamrow = self.exposure.header.beamposrow
        beamcol = self.exposure.header.beamposcol
        if self.sender() is self.beamXDoubleSpinBox:
            beamcol = (value, beamcol[1])
        elif self.sender() is self.beamYDoubleSpinBox:
            beamrow = (value, beamrow[1])
        elif self.sender() is self.beamXErrDoubleSpinBox:
            beamcol = (beamcol[0], value)
        elif self.sender() is self.beamYErrDoubleSpinBox:
            beamrow = (beamrow[0], value)
        else:
            assert False
        self.updateBeamPosition(beamrow, beamcol)

    @Slot()
    def saveParameter(self):
        if self.exposure is None:
            return
        if self.sender() is self.saveSDDistToolButton:
            self.instrument.config['geometry']['dist_sample_det'] = float(self.dist_sample_det[0])
            self.instrument.config['geometry']['dist_sample_det.err'] = float(self.dist_sample_det[1])
            logger.info(f'Updated sample-to-detector distance to {self.dist_sample_det[0]:.5f} \xb1 {self.dist_sample_det[1]:.5f} mm')
        elif self.sender() == self.saveBeamXToolButton:
            self.instrument.config['geometry']['beamposy'] = self.exposure.header.beamposcol[0]
            self.instrument.config['geometry']['beamposy.err'] = self.exposure.header.beamposcol[1]
            logger.info(f'Updated beam column (X) coordinate to {self.exposure.header.beamposcol[0]:.5f} \xb1 '
                        f'{self.exposure.header.beamposcol[1]:.5f} pixel')
        elif self.sender() == self.saveBeamYToolButton:
            self.instrument.config['geometry']['beamposx'] = self.exposure.header.beamposrow[0]
            self.instrument.config['geometry']['beamposx.err'] = self.exposure.header.beamposrow[1]
            logger.info(f'Updated beam row (Y) coordinate to {self.exposure.header.beamposrow[0]:.5f} \xb1 '
                        f'{self.exposure.header.beamposrow[1]:.5f} pixel')
        else:
            assert False
        self.sender().setEnabled(False)

    @Slot()
    def addPair(self):
        twi = QtWidgets.QTreeWidgetItem()
        pixval = self.uncalibratedValDoubleSpinBox.value()
        pixunc = self.uncalibratedErrDoubleSpinBox.value()
        qval = self.calibratedValDoubleSpinBox.value()
        qunc = self.calibratedErrDoubleSpinBox.value()
        twi.setData(0, QtCore.Qt.DisplayRole, f'{pixval:.4f} \xb1 {pixunc:.4f}')
        twi.setData(0, QtCore.Qt.UserRole, (pixval, pixunc))
        twi.setData(1, QtCore.Qt.DisplayRole, f'{qval:.4f} \xb1 {qunc:.4f}')
        twi.setData(1, QtCore.Qt.UserRole, (qval, qunc))
        self.pairsTreeWidget.addTopLevelItem(twi)
        self.pairsTreeWidget.resizeColumnToContents(0)
        self.pairsTreeWidget.resizeColumnToContents(1)
        self.calibrate()

    @Slot()
    def removePair(self):
        for item in self.pairsTreeWidget.selectedItems():
            self.pairsTreeWidget.takeTopLevelItem(self.pairsTreeWidget.indexOfTopLevelItem(item))
        self.calibrate()

    def plotCalibrationLine(self):
        pixval, pixunc, qval, qunc, wavelength, pixelsize = self.calibrationDataset()
        self.axes.clear()
        if pixval.size == 0:
            self.canvas.draw_idle()
            return
        l = self.axes.errorbar(pixval, qval, qunc, pixunc, '.')
        self.axes.errorbar([0], [0], [0], [0], '.', color=l[0].get_color())
        pix = np.linspace(0, pixval.max(), 100)
        q = 4 * np.pi * np.sin(0.5 * np.arctan((pix * pixelsize[0]) / self.sdDistDoubleSpinBox.value())) / wavelength[0]
        self.axes.plot(pix, q, 'r-')
        self.axes.set_xlabel('Distance from origin (pixel)')
        self.axes.set_ylabel('$q$ (nm$^{-1}$)')
        self.axes.grid(True, which='both')
        self.canvas.draw_idle()

    def calibrationDataset(self):
        pixval = np.array([self.pairsTreeWidget.topLevelItem(i).data(0, QtCore.Qt.UserRole)[0] for i in
                           range(self.pairsTreeWidget.topLevelItemCount())])
        pixunc = np.array([self.pairsTreeWidget.topLevelItem(i).data(0, QtCore.Qt.UserRole)[1] for i in
                           range(self.pairsTreeWidget.topLevelItemCount())])
        qval = np.array([self.pairsTreeWidget.topLevelItem(i).data(1, QtCore.Qt.UserRole)[0] for i in
                         range(self.pairsTreeWidget.topLevelItemCount())])
        qunc = np.array([self.pairsTreeWidget.topLevelItem(i).data(1, QtCore.Qt.UserRole)[1] for i in
                         range(self.pairsTreeWidget.topLevelItemCount())])
        wavelength = self.instrument.config['geometry']['wavelength'], self.instrument.config['geometry']['wavelength.err']
        pixelsize = self.exposure.header.pixelsize
        return pixval, pixunc, qval, qunc, wavelength, pixelsize

    def calibrate(self):
        pixval, pixunc, qval, qunc, wavelength, pixelsize = self.calibrationDataset()
        if pixval.size == 0:
            return
        ql_div_4pi = (  # q * wavelength / (4pi)
            qval * wavelength[0] / 4 / np.pi,
            ((qval * wavelength[1]) ** 2 + (qunc * wavelength[0]) ** 2) ** 0.5 / 4 / np.pi
        )
        logger.debug(f'{ql_div_4pi=}')
        asinx2_ql_div_4pi = (
            np.arcsin(ql_div_4pi[0]) * 2,
            2 / (1 - ql_div_4pi[0] ** 2) ** 0.5 * ql_div_4pi[1],
        )
        logger.debug(f'{asinx2_ql_div_4pi=}')
        tg_2asin_ql_div_4pi = (
            np.tan(asinx2_ql_div_4pi[0]),
            (1 + np.tan(asinx2_ql_div_4pi[0]) ** 2) * asinx2_ql_div_4pi[1]
        )
        logger.debug(f'{tg_2asin_ql_div_4pi=}')
        tg_2asin_ql_div_4pi_div_pixsize = (
            tg_2asin_ql_div_4pi[0] / pixelsize[0],
            (((tg_2asin_ql_div_4pi[0] * pixelsize[1]) / pixelsize[0] ** 2) ** 2 + (
                    tg_2asin_ql_div_4pi[1] / pixelsize[0]) ** 2) ** 0.5
        )
        logger.debug(f'{tg_2asin_ql_div_4pi_div_pixsize=}')
        if len(pixval) == 1:
            # no fitting, just calculate L directly: L = pixel / (tan(2*asin(q*lambda/4pi)) / pixsize)
            L = (
                pixval[0] / tg_2asin_ql_div_4pi_div_pixsize[0][0],
                ((pixunc[0] / tg_2asin_ql_div_4pi_div_pixsize[0][0]) ** 2 +
                 (pixval[0] * tg_2asin_ql_div_4pi_div_pixsize[1][0] / tg_2asin_ql_div_4pi_div_pixsize[0][
                     0] ** 2) ** 2) ** 0.5
            )
        else:
            # fitting:    pixel = L * tan(2*asin(q*lambda/4pi))
            data = scipy.odr.RealData(x=tg_2asin_ql_div_4pi_div_pixsize[0], sx=tg_2asin_ql_div_4pi_div_pixsize[1],
                                      y=pixval, sy=pixunc)
            logger.debug(f'{data.x=}, {data.y=}, {data.sx=}, {data.sy=}')
            model = scipy.odr.Model(lambda L, x: L * x)
            odr = scipy.odr.ODR(data, model, [1.0])
            result = odr.run()
            L = result.beta[0], result.sd_beta[0]
        logger.debug(f'{L=}')
        self.sdDistDoubleSpinBox.setValue(L[0])
        self.sdDistErrDoubleSpinBox.setValue(L[1])
        self.saveSDDistToolButton.setEnabled(True)
        self.dist_sample_det = L
        self.plotCalibrationLine()

    @Slot()
    def fitPeak(self):
        if (self.curve is None) or (self.exposure is None):
            return
        xmin, xmax, ymin, ymax = self.plotcurve.getRange()
        curve = self.curve.trim(xmin, xmax, ymin, ymax, bypixel=True)
        try:
            parameters, covariance, peakfcn = fitpeak(
                curve.pixel, curve.intensity, dx=None, dy=None,
                peaktype=PeakType.Lorentzian if self.sender() == self.fitLorentzPushButton else PeakType.Gaussian)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, 'Error while fitting', f'An error happened while fitting: {exc}.\n'
                                           'Please select a different algorithm, a different range in the curve or '
                                           'select an approximate beam position manually and start over.')
            return
        x = np.linspace(curve.pixel.min(), curve.pixel.max(), 100)
        fitcurve = Curve.fromVectors(q=np.interp(x, curve.pixel, curve.q), intensity=peakfcn(x), pixel=x)
        self.plotcurve.addCurve(fitcurve, color='r', lw=1, ls='-', marker='')
        self.plotcurve.replot()
        self.uncalibratedValDoubleSpinBox.setValue(parameters[1])
        self.uncalibratedErrDoubleSpinBox.setValue(covariance[1, 1] ** 0.5)

    @Slot()
    def calibrantChanged(self):
        if self.calibrantComboBox.currentIndex() < 0:
            return
        calibrant = \
            [c for c in self.instrument.calibrants.qcalibrants() if c.name == self.calibrantComboBox.currentText()][0]
        assert isinstance(calibrant, QCalibrant)
        self.peakComboBox.clear()
        self.peakComboBox.addItems([name for name, val, unc in calibrant.peaks])
        self.peakComboBox.setCurrentIndex(0)

    @Slot()
    def onCalibrantPeakSelected(self):
        if self.calibrantComboBox.currentIndex() < 0:
            return
        calibrant = \
            [c for c in self.instrument.calibrants.qcalibrants() if c.name == self.calibrantComboBox.currentText()][0]
        assert isinstance(calibrant, QCalibrant)
        if self.peakComboBox.currentIndex() < 0:
            return
        val, unc = [(val, unc) for name, val, unc in calibrant.peaks if name == self.peakComboBox.currentText()][0]
        self.calibratedValDoubleSpinBox.setValue(val)
        self.calibratedErrDoubleSpinBox.setValue(unc)

    @Slot()
    def populateCalibrants(self):
        self.calibrantComboBox.clear()
        self.calibrantComboBox.addItems(sorted([c.name for c in self.instrument.calibrants.qcalibrants()]))
        self.selectCalibrantForExposure()

    def selectCalibrantForExposure(self):
        if self.exposure is None:
            return
        names = [c.name for c in self.instrument.calibrants.qcalibrants() if
                 re.match(c.regex, self.exposure.header.title) is not None]
        if names:
            self.calibrantComboBox.setCurrentIndex(self.calibrantComboBox.findText(names[0]))
            self.calibrantChanged()

    def on2DPick(self, event: PickEvent):
        if self.manualcursor is not None:
            if (event.mouseevent.button == 1):
                beamcol, beamrow = event.mouseevent.xdata, event.mouseevent.ydata
                self.updateBeamPosition((beamrow, 0), (beamcol, 0))
            self.manualcursor.set_active(False)
            self.manualcursor = None

    @Slot(str, int)
    def onFSNSelected(self, prefix: str, index: int):
        logger.debug(f'FSN selected: {prefix=} {index=}')
        self.setExposure(self.instrument.io.loadExposure(prefix, index, raw=True, check_local=True))

    def setExposure(self, exposure: Exposure):
        self.exposure = exposure
        self.plotimage.setExposure(self.exposure)
        self.plotcurve.clear()
        pixmin, pixmax = self.exposure.validpixelrange()
        numpoints = int(np.ceil(abs(pixmax - pixmin)))
        if self.pixMinCheckBox.isChecked():
            pixmin = self.pixMinDoubleSpinBox.value()
        else:
            self.pixMinDoubleSpinBox.setValue(pixmin)
        if self.pixMaxCheckBox.isChecked():
            pixmax = self.pixMaxDoubleSpinBox.value()
        else:
            self.pixMaxDoubleSpinBox.setValue(pixmax)
        if self.numPointsCheckBox.isChecked():
            numpoints = self.numPointsSpinBox.value()
        else:
            self.numPointsSpinBox.setValue(numpoints)
        if self.logSpacedPixelsCheckBox.isChecked():
            pixrange = np.geomspace(pixmin, pixmax, numpoints)
        else:
            pixrange = np.linspace(pixmin, pixmax, numpoints)
        self.curve = self.exposure.radial_average(self.exposure.pixeltoq(pixrange))
        self.plotcurve.addCurve(self.curve)
        self.plotcurve.setPixelMode(True)
        for spinbox in [self.beamXDoubleSpinBox, self.beamYDoubleSpinBox, self.beamXErrDoubleSpinBox, self.beamYErrDoubleSpinBox]:
            spinbox.blockSignals(True)
        self.beamXDoubleSpinBox.setValue(self.exposure.header.beamposcol[0])
        self.beamXErrDoubleSpinBox.setValue(self.exposure.header.beamposcol[1])
        self.beamYDoubleSpinBox.setValue(self.exposure.header.beamposrow[0])
        self.beamYErrDoubleSpinBox.setValue(self.exposure.header.beamposrow[1])
        for spinbox in [self.beamXDoubleSpinBox, self.beamYDoubleSpinBox, self.beamXErrDoubleSpinBox, self.beamYErrDoubleSpinBox]:
            spinbox.blockSignals(False)
        self.saveBeamXToolButton.setEnabled(False)
        self.saveBeamYToolButton.setEnabled(False)
        self.selectCalibrantForExposure()

    @Slot()
    def findCenter(self):
        if (self.exposure is None) or (self.curve is None):
            return
        xmin, xmax, ymin, ymax = self.plotcurve.getRange()
        logger.debug(f'Range: {xmin=}, {xmax=}, {ymin=}, {ymax=}')
        if self.curve is None:
            return
        curve = self.curve.trim(xmin, xmax, ymin, ymax, bypixel=True)
        logger.debug(f'Trimmed curve has {len(curve)} points')
        rmin = curve.pixel.min()
        rmax = curve.pixel.max()
        logger.debug(f'{rmin=}, {rmax=}')
        algorithm = centeringalgorithms[self.centeringMethodComboBox.currentText()]
        self.updateBeamPosition(
            *findbeam(algorithm, self.exposure, rmin, rmax, 0, 0, eps=self.finiteDifferenceDeltaDoubleSpinBox.value()))

    def updateBeamPosition(self, row: Tuple[float, float], col: Tuple[float, float]):
        if self.exposure is None:
            # no exposure loaded yet
            return
        self.exposure.header.beamposrow = row
        self.exposure.header.beamposcol = col
        self.setExposure(self.exposure)
        self.saveBeamXToolButton.setEnabled(True)
        self.saveBeamYToolButton.setEnabled(True)

    @Slot()
    def manualCentering(self):
        if self.manualcursor is not None:
            return
        self.manualcursor = Cursor(self.plotimage.axes, horizOn=True, vertOn=True, useblit=False, color='red', lw='1')

    @Slot()
    def getCentreOfGravity(self):
        colmin, colmax, rowmin, rowmax = self.plotimage.axes.axis()
        row = np.arange(self.exposure.shape[0])
        col = np.arange(self.exposure.shape[1])
        idxrow = np.logical_and(row >= min(rowmin, rowmax), row<=max(rowmin, rowmax))
        idxcol = np.logical_and(col >= min(colmin, colmax), col<=max(colmin, colmax))
        mask = np.logical_and(
            self.exposure.mask,
            np.logical_and(idxrow[:,np.newaxis], idxcol[np.newaxis, :])
        )
        smallimg = self.exposure.intensity[np.logical_and(idxrow[:,np.newaxis], idxcol[np.newaxis, :])]
        smallrow = row[idxrow]
        smallcol = col[idxcol]
        sumimg = self.exposure.intensity[mask>0].sum()
        bcrow = (smallrow[:, np.newaxis] * smallimg).sum() / sumimg
        bccol = (smallcol[np.newaxis, :] * smallimg).sum() / sumimg
        self.updateBeamPosition((bcrow, 0), (bccol, 0))
