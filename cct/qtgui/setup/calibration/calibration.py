import numpy as np
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.widgets import Cursor
from sastool.classes2 import Exposure
from sastool.misc.basicfit import findpeak_asymmetric
from sastool.misc.easylsq import nonlinear_odr
from sastool.misc.errorvalue import ErrorValue
from sastool.utils2d import centering2

from .calibration_ui import Ui_MainWindow
from .pairstore import PairStore
from ...core.fsnselector import FSNSelector
from ...core.mixins import ToolWindow
from ...core.plotcurve import PlotCurve
from ...core.plotimage import PlotImage
from ....core.instrument.instrument import Instrument
from ....core.utils.inhibitor import Inhibitor


class Calibration(QtWidgets.QMainWindow, Ui_MainWindow, ToolWindow):
    fsnSelector: FSNSelector
    plotImage: PlotImage
    plotCurve: PlotCurve
    distCalibFigure: Figure
    distCalibFigureCanvas: FigureCanvasQTAgg
    distCalibFigureToolbar: NavigationToolbar2QT
    distCalibAxes: Axes
    pairsStore: PairStore
    cursor: Cursor
    centeringState: centering2.Centering = None

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        self._updating_ui = Inhibitor()
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, MainWindow):
        Ui_MainWindow.setupUi(self, MainWindow)
        self.fsnselectorPage.setLayout(QtWidgets.QVBoxLayout())
        self.fsnSelector = FSNSelector(self.fsnselectorPage, credo=self.credo)
        self.fsnselectorPage.layout().addWidget(self.fsnSelector)
        self.tab2D.setLayout(QtWidgets.QVBoxLayout())
        self.plotImage = PlotImage(self.tab2D, register_instance=False)
        self.tab2D.layout().addWidget(self.plotImage)
        self.fsnSelector.FSNSelected.connect(self.onFSNSelected)
        self.tab1D.setLayout(QtWidgets.QVBoxLayout())
        self.plotCurve = PlotCurve(self.tab1D)
        self.tab1D.layout().addWidget(self.plotCurve)
        self.distCalibFigure = Figure()
        self.distCalibFigureCanvas = FigureCanvasQTAgg(self.distCalibFigure)
        self.tabDistance.setLayout(QtWidgets.QVBoxLayout())
        self.tabDistance.layout().addWidget(self.distCalibFigureCanvas)
        self.distCalibFigureToolbar = NavigationToolbar2QT(self.distCalibFigureCanvas, self.tabDistance)
        self.tabDistance.layout().addWidget(self.distCalibFigureToolbar)
        self.distCalibAxes = self.distCalibFigure.add_subplot(1, 1, 1)
        self.centeringMethodComboBox.addItems(sorted(centering2.Centering.algorithmname.values()) + ['Manual (click)'])
        self.centeringMethodComboBox.setCurrentIndex(0)
        self.centeringMethodComboBox.currentIndexChanged.connect(self.onCenteringMethodChanged)
        self.onCenteringMethodChanged()
        self.centeringPushButton.clicked.connect(self.onCenteringRequested)
        self.plotImage.setOnlyAbsPixel()
        self.beamXDoubleSpinBox.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
        self.beamYDoubleSpinBox.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
        self.sdDistDoubleSpinBox.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
        self.beamXErrDoubleSpinBox.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
        self.beamYErrDoubleSpinBox.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
        self.sdDistErrDoubleSpinBox.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
        self.saveBeamXPushButton.clicked.connect(self.onSaveResult)
        self.saveBeamYPushButton.clicked.connect(self.onSaveResult)
        self.saveSDDistPushButton.clicked.connect(self.onSaveResult)
        self.fitLorentzPushButton.clicked.connect(self.onLorentzFit)
        self.fitGaussPushButton.clicked.connect(self.onGaussFit)
        self.calibrantComboBox.addItems(sorted(self.credo.config['calibrants']))
        self.calibrantComboBox.currentIndexChanged.connect(self.onCalibrantChanged)
        self.addPairPushButton.clicked.connect(self.onAddPair)
        self.removePairPushButton.clicked.connect(self.onRemovePair)
        self.peakComboBox.currentIndexChanged.connect(self.onPeakChosen)
        self.calibrantComboBox.setCurrentIndex(0)
        self.onCalibrantChanged()
        assert isinstance(self.pairsTreeView, QtWidgets.QTreeView)
        self.pairsStore = PairStore()
        self.pairsTreeView.setModel(self.pairsStore)
        self.distCalibFigureCanvas.mpl_connect('resize_event', self.onCanvasResize)

    def onCanvasResize(self, event):
        self.distCalibFigure.tight_layout()
        self.distCalibFigureCanvas.draw()

    def cleanup(self):
        self.fsnSelector.close()
        super().cleanup()

    def onAddPair(self):
        self.pairsStore.addPair(
            ErrorValue(self.uncalibratedValDoubleSpinBox.value(), self.uncalibratedErrDoubleSpinBox.value()),
            ErrorValue(self.calibratedValDoubleSpinBox.value(), self.calibratedErrDoubleSpinBox.value()))
        for c in range(self.pairsStore.columnCount()):
            self.pairsTreeView.resizeColumnToContents(c)
        self.recalculateDistance()

    def recalculateDistance(self):
        pairs = self.pairsStore.pairs()
        wl = ErrorValue(self.credo.config['geometry']['wavelength'],
                        self.credo.config['geometry']['wavelength.err'])
        if not pairs:
            self.plotPairs()
            return
        if len(pairs) == 1:
            # calculate the distance directly
            dist = pairs[0][0] * self.credo.config['geometry']['pixelsize'] / (
                ((pairs[0][1] * wl / 4 / np.pi).arcsin() * 2.0).tan())
        else:
            pix = [p[0] for p in pairs]
            q = [p[1] for p in pairs]
            rho = [p * self.credo.config['geometry']['pixelsize'] for p in pix]  # pixel * pixelsize
            qlambda = [q_ * wl for q_ in q]  # q * lambda
            dist, stat = nonlinear_odr(
                [r.val for r in rho], [ql.val for ql in qlambda],
                [r.err for r in rho], [ql.err for ql in qlambda],
                lambda rho_, L: 4 * np.pi * np.sin(0.5 * np.arctan(rho_ / L)), [100, ])
        self.sdDistDoubleSpinBox.setValue(dist.val)
        self.sdDistErrDoubleSpinBox.setValue(dist.err)
        self.plotPairs()

    def onRemovePair(self):
        assert isinstance(self.pairsTreeView, QtWidgets.QTreeView)
        try:
            idx = self.pairsTreeView.selectedIndexes()[0]
            self.pairsStore.removePair(idx.row())
        except IndexError:
            pass
        self.recalculateDistance()

    def onCalibrantChanged(self):
        calibrant = self.calibrantComboBox.currentText()
        with self._updating_ui:
            self.peakComboBox.clear()
            self.peakComboBox.addItems(sorted(self.credo.config['calibrants'][calibrant]))
        self.peakComboBox.setCurrentIndex(0)
        self.onPeakChosen()

    def onPeakChosen(self):
        if self._updating_ui:
            return
        peak = self.credo.config['calibrants'][self.calibrantComboBox.currentText()][self.peakComboBox.currentText()]
        self.calibratedValDoubleSpinBox.setValue(peak['val'])
        self.calibratedErrDoubleSpinBox.setValue(peak['err'])

    def plotPairs(self):
        self.distCalibAxes.clear()
        try:
            pairs = self.pairsStore.pairs()
            if not pairs:
                return
            pix = [p[0].val for p in pairs]
            dpix = [p[0].err for p in pairs]
            q = [p[1].val for p in pairs]
            dq = [p[1].err for p in pairs]
            self.distCalibAxes.errorbar(pix, q, dq, dpix, 'bo', label='Calibration pairs')
            dist = self.sdDistDoubleSpinBox.value()
            pix = np.linspace(0, max(pix), 1000)
            q = 4 * np.pi * np.sin(0.5 * np.arctan(pix * self.credo.config['geometry']['pixelsize'] / dist)) / \
                self.credo.config['geometry']['wavelength']
            self.distCalibAxes.plot(pix, q, 'r-', label='Fitted curve')
            assert isinstance(self.distCalibAxes, Axes)
            self.distCalibAxes.set_xlabel('Pixel coordinate')
            self.distCalibAxes.set_ylabel('q (nm$^{-1}$)')
            self.distCalibAxes.legend(loc='best')
        finally:
            self.distCalibFigureCanvas.draw()

    def onLorentzFit(self):
        return self.fit('Lorentz')

    def fit(self, curvetype):
        rad = self.plotImage.exposure().radial_average(pixel=True)
        xmin, xmax, ymin, ymax = self.plotCurve.getZoomRange()
        rad = rad.trim(xmin, xmax, ymin, ymax)
        x = np.linspace(rad.q.min(), rad.q.max())
        peak, hwhm1, hwhm2, baseline, amplitude, y = findpeak_asymmetric(rad.q, rad.Intensity, rad.Error,
                                                                         curve=curvetype,
                                                                         return_x=x)
        self.uncalibratedValDoubleSpinBox.setValue(peak.val)
        self.uncalibratedErrDoubleSpinBox.setValue(peak.err)
        self.plotCurve.addFitCurve(x, y, color='r', ls='-')

    def onGaussFit(self):
        return self.fit('Gauss')

    def onDoubleSpinBoxValueChanged(self):
        if self._updating_ui:
            return
        if self.sender() in [self.beamXDoubleSpinBox, self.beamXErrDoubleSpinBox]:
            self.saveBeamXPushButton.setEnabled(True)
        elif self.sender() in [self.beamYDoubleSpinBox, self.beamYErrDoubleSpinBox]:
            self.saveBeamYPushButton.setEnabled(True)
        elif self.sender() in [self.sdDistDoubleSpinBox, self.sdDistErrDoubleSpinBox]:
            self.saveSDDistPushButton.setEnabled(True)
        else:
            raise ValueError(self.sender())

    def onSaveResult(self):
        assert isinstance(self.credo, Instrument)
        if self.sender() is self.saveBeamXPushButton:
            self.credo.config['geometry']['beamposx'] = self.beamYDoubleSpinBox.value()
            self.credo.config['geometry']['beamposx.err'] = self.beamYErrDoubleSpinBox.value()
        elif self.sender() is self.saveBeamYPushButton:
            self.credo.config['geometry']['beamposy'] = self.beamXDoubleSpinBox.value()
            self.credo.config['geometry']['beamposy.err'] = self.beamXErrDoubleSpinBox.value()
        elif self.sender() is self.saveSDDistPushButton:
            self.credo.config['geometry']['dist_sample_det'] = self.sdDistDoubleSpinBox.value()
            self.credo.config['geometry']['dist_sample_det.err'] = self.sdDistErrDoubleSpinBox.value()
        else:
            raise ValueError(self.sender())
        self.sender().setEnabled(False)
        self.credo.emit_config_change_signal()

    def onFSNSelected(self, fsn: int, prefix: str, exposure: Exposure):
        self.plotImage.setExposure(exposure)
        self.plotCurve.clear()
        self.plotCurve.addCurve(exposure.radial_average(pixel=True), label=exposure.header.title, hold_mode=False,
                                color='blue', ls='-', marker='.')
        self.plotCurve.setXLabel('Pixel coordinate')
        self.plotCurve.setYLabel('Total counts')
        mask = np.logical_and(exposure.mask!=0, np.isfinite(exposure.intensity)).astype(np.uint8)
        self.centeringState = centering2.Centering(exposure.intensity, mask,
                                                   [exposure.header.beamcentery.val, exposure.header.beamcenterx.val])
        with self._updating_ui:
            self.beamXDoubleSpinBox.setValue(exposure.header.beamcenterx.val)
            self.beamXErrDoubleSpinBox.setValue(exposure.header.beamcenterx.err)
            self.beamYDoubleSpinBox.setValue(exposure.header.beamcentery.val)
            self.beamYErrDoubleSpinBox.setValue(exposure.header.beamcentery.err)
            self.sdDistDoubleSpinBox.setValue(exposure.header.distance.val)
            self.sdDistErrDoubleSpinBox.setValue(exposure.header.distance.err)

    def newBeamPosFound(self, posx, posy):
        exposure = self.plotImage.exposure()
        exposure.header.beamcentery = posy
        exposure.header.beamcenterx = posx
        self.beamXDoubleSpinBox.setValue(exposure.header.beamcenterx.val)
        self.beamXErrDoubleSpinBox.setValue(exposure.header.beamcenterx.err)
        self.beamYDoubleSpinBox.setValue(exposure.header.beamcentery.val)
        self.beamYErrDoubleSpinBox.setValue(exposure.header.beamcentery.err)
        self.onFSNSelected(exposure.header.fsn, '', exposure)

    def onCenteringRequested(self):
        exposure = self.plotImage.exposure()
        if self.centeringMethodComboBox.currentText() == 'Manual (click)':
            # this algorithm is implemented here.
            self.tabWidget.setCurrentWidget(self.tab2D)
            self.cursor = Cursor(self.plotImage.axes, zorder=100)
            self.cursor.connect_event('button_press_event', self.onCursorPressed)
        else:
            # all other methods are implemented in sastool.
            method = [k for k, v in centering2.Centering.algorithmname.items() if
                      v == self.centeringMethodComboBox.currentText()][0]
            try:
                xmin1d, xmax1d, ymin1d, ymax1d = self.plotCurve.getZoomRange()
                if method == 'coi':
                    # center of gravity needs an area of the 2D image.
                    colmin, colmax, rowmin, rowmax = self.plotImage.axes.axis()
                    posy, posx = self.centeringState.findcenter('coi', min(rowmin, rowmax), max(rowmin, rowmax),
                                                                min(colmin, colmax), max(colmin, colmax))
                elif method == 'slices':
                    posy, posx = self.centeringState.findcenter('slices', xmin1d, xmax1d)
                elif method == 'azimuthal':
                    posy, posx = self.centeringState.findcenter('azimuthal', xmin1d, xmax1d)
                elif method == 'azimuthal_fold':
                    posy, posx = self.centeringState.findcenter('azimuthal_fold', xmin1d, xmax1d)
                elif method == 'peak_amplitude':
                    posy, posx = self.centeringState.findcenter('peak_amplitude', xmin1d, xmax1d)
                elif method == 'peak_width':
                    posy, posx = self.centeringState.findcenter('peak_width', xmin1d, xmax1d)
                elif method == 'powerlaw':
                    posy, posx = self.centeringState.findcenter('powerlaw', xmin1d, xmax1d)
                else:
                    raise ValueError('Invalid centering algorithm: {}'.format(method))
                if not self.centeringState.lastresults.success:
                    QtWidgets.QMessageBox.warning(
                        self, 'Warning',
                        'Centering might not have been successful\nMessage: {}\nStatus: {}'.format(
                            self.centeringState.lastresults.message,
                            self.centeringState.lastresults.status))
                self.newBeamPosFound(posx, posy)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, 'Error while centering', exc.args[0])

    def onCursorPressed(self, event: MouseEvent):
        if not ((event.inaxes is self.plotImage.axes) and (event.button == 1)):
            return
        assert isinstance(self.cursor, Cursor)
        self.cursor.horizOn = False
        self.cursor.vertOn = False
        self.cursor.visible = False
        self.cursor.disconnect_events()
        self.cursor.set_active(False)
        del self.cursor
        self.plotImage.canvas.draw()
        self.newBeamPosFound(event.xdata, event.ydata)

    def onCenteringMethodChanged(self):
        if self.centeringMethodComboBox.currentText() == 'Manual (click)':
            self.centeringDescriptionTextBrowser.setText(
                'After clicking the "Find center" button, select the desired beam center on the 2D image with the blue '
                'crosshair cursor, then press the left mouse button.')
        else:
            method = [k for k, v in centering2.Centering.algorithmname.items() if
                      v == self.centeringMethodComboBox.currentText()][0]
            self.centeringDescriptionTextBrowser.setText(centering2.Centering.algorithmdescription[method])
