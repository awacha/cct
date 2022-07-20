import logging
from typing import Optional, Tuple

from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSlot as Slot
from matplotlib.axes import Axes, np
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import lmfit

from .capillarysizer_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.algorithms.peakfit import fitpeak, PeakType
from ....core2.algorithms.capillarytransmission import capillarytransmission
from ....core2.dataclasses import Scan

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CapillarySizer(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    figure: Figure
    figtoolbar: NavigationToolbar2QT
    canvas: FigureCanvasQTAgg
    axes: Axes
    scan: Optional[Scan] = None
    positive: Tuple[float, float] = (.0, .0)
    negative: Tuple[float, float] = (.0, .0)
    line: Line2D = None
    positivepeakline: Optional[Line2D] = None
    negativepeakline: Optional[Line2D] = None
    profilefitline: Optional[Line2D] = None
    center: Tuple[float, float] = (.0, .0)
    thickness: Tuple[float, float] = (.0, .0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figtoolbar = NavigationToolbar2QT(self.canvas, self)
        self.figureVerticalLayout.addWidget(self.canvas)
        self.figureVerticalLayout.addWidget(self.figtoolbar)
        self.axes = self.figure.add_subplot(self.figure.add_gridspec(1, 1)[:, :])
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self.canvas.draw_idle()
        self.scanIndexSpinBox.valueChanged.connect(self.scanIndexChanged)
        self.signalNameComboBox.currentIndexChanged.connect(self.signalNameChanged)
        self.fitNegativeToolButton.clicked.connect(self.fitPeak)
        self.fitPositiveToolButton.clicked.connect(self.fitPeak)
        self.sampleNameComboBox.currentIndexChanged.connect(self.sampleChanged)
        self.sampleNameComboBox.setModel(self.instrument.samplestore.sortedmodel)
        self.negativeValDoubleSpinBox.valueChanged.connect(self.setValuesFromSpinboxes)
        self.positiveValDoubleSpinBox.valueChanged.connect(self.setValuesFromSpinboxes)
        self.negativeErrDoubleSpinBox.valueChanged.connect(self.setValuesFromSpinboxes)
        self.positiveErrDoubleSpinBox.valueChanged.connect(self.setValuesFromSpinboxes)
        self.updateCenterToolButton.clicked.connect(self.saveCenter)
        self.updateThicknessToolButton.clicked.connect(self.saveThickness)
        self.updateCenterToolButton.setIcon(
            QtWidgets.QApplication.instance().style().standardIcon(QtWidgets.QStyle.SP_ArrowRight))
        self.updateThicknessToolButton.setIcon(
            QtWidgets.QApplication.instance().style().standardIcon(QtWidgets.QStyle.SP_ArrowRight))
        self.instrument.scan.lastscanchanged.connect(self.onLastScanChanged)
        if self.instrument.scan.firstscan() is None:
            self.scanIndexSpinBox.setEnabled(False)
        else:
            self.scanIndexSpinBox.setRange(self.instrument.scan.firstscan(), self.instrument.scan.lastscan())
        self.derivativeToolButton.toggled.connect(self.signalNameChanged)
        if self.instrument.scan.lastscan() is not None:
            self.scanIndexSpinBox.setValue(self.instrument.scan.lastscan())
        self.signalNameComboBox.setCurrentIndex(0)
        self.reloadToolButton.clicked.connect(self.signalNameChanged)
        self.profileFitPushButton.clicked.connect(self.fitProfile)
        self.replot()

    @Slot()
    def fitProfile(self):
        x = self.line.get_xdata()
        y = self.line.get_ydata()
        xmin, xmax, ymin, ymax = self.axes.axis()
        idx = np.logical_and(
            np.logical_and(x >= xmin, x <= xmax),
            np.logical_and(y >= ymin, y <= ymax)
        )

        model = lmfit.Model(self.capillarytransmissionmodel)
        params = model.make_params(
            I0=self.profileFitI0DoubleSpinBox.value(),
            center=self.profileFitPositionDoubleSpinBox.value(),
            outerdiameter=self.profileFitOuterDiameterDoubleSpinBox.value(),
            wallthickness=self.profileFitWallThicknessDoubleSpinBox.value(),
            sampleabsorptionlength=self.profileFitSampleAbsorptionLengthDoubleSpinBox.value(),
            wallabsorptionlength=self.profileFitWallAbsorptionLengthDoubleSpinBox.value(),
            beamsigma=self.profileFitBeamSigmaDoubleSpinBox.value(),
            Nbeam=self.profileFitNBeamSpinBox.value()
        )
        params['I0'].min = 0
        params['I0'].vary = self.profileFitI0CheckBox.isChecked()
        params['center'].min = np.nanmin(x[idx])
        params['center'].max = np.nanmax(x[idx])
        params['center'].vary = self.profileFitPositionCheckBox.isChecked()
        params['outerdiameter'].min = 0
        params['outerdiameter'].max = np.nanmax(x[idx]) - np.nanmin(x[idx])
        params['outerdiameter'].vary = self.profileFitOuterDiameterCeckBox.isChecked()
        params['wallthickness'].min = 0
        params['wallthickness'].max = params['outerdiameter']
        params['wallthickness'].vary = self.profileFitWallThicknessCheckBox.isChecked()
        params['sampleabsorptionlength'].min = 10**self.profileFitSampleAbsorptionLengthDoubleSpinBox.decimals()
        params['sampleabsorptionlength'].max = self.profileFitSampleAbsorptionLengthDoubleSpinBox.maximum()
        params['sampleabsorptionlength'].vary = self.profileFitSampleAbsorptionLengthCheckBox.isChecked()
        params['wallabsorptionlength'].min = 10**self.profileFitWallAbsorptionLengthDoubleSpinBox.decimals()
        params['wallabsorptionlength'].max = self.profileFitWallAbsorptionLengthDoubleSpinBox.maximum()
        params['wallabsorptionlength'].vary = self.profileFitWallAbsorptionLengthCheckBox.isChecked()
        params['beamsigma'].min = 10**self.profileFitBeamSigmaDoubleSpinBox.decimals()
        params['beamsigma'].max = 0.5*(np.nanmax(x[idx])-np.nanmin(x[idx]))
        params['beamsigma'].vary = self.profileFitBeamSigmaCheckBox.isChecked()
        params['Nbeam'].vary = False
        result = model.fit(y[idx], params, x=x[idx])
        for parname, doublespinbox, label in [
            ('I0', self.profileFitI0DoubleSpinBox, self.profileFitI0UncertaintyLabel),
            ('center', self.profileFitPositionDoubleSpinBox, self.profileFitPositionUncertaintyLabel),
            ('outerdiameter', self.profileFitOuterDiameterDoubleSpinBox, self.profileFitOuterDiameterUncertaintyLabel),
            ('wallthickness', self.profileFitWallThicknessDoubleSpinBox, self.profileFitWallThicknessUncertaintyLabel),
            ('sampleabsorptionlength', self.profileFitSampleAbsorptionLengthDoubleSpinBox, self.profileFitSampleAbsorptionLengthUncertaintyLabel),
            ('wallabsorptionlength', self.profileFitWallAbsorptionLengthDoubleSpinBox, self.profileFitWallAbsorptionLengthUncertaintyLabel),
            ('beamsigma', self.profileFitBeamSigmaDoubleSpinBox, self.profileFitBeamSigmaUncertaintyLabel),
        ]:
            doublespinbox.setValue(result.params[parname].value)
            if result.parameter[parname].stderr is None:
                label.setText('(fixed)')
            else:
                label.setText(f'{result.params[parname].stderr:.4f}')
        self.newPositionLabel.setText(f'{result.params["center"].value:.4f} \xb1 {result.params["center"].stderr:.4f}')
        self.newThicknessLabel.setText(f'{result.params["outerdiameter"].value/10:.4f} \xb1 {result.params["outerdiameter"].stderr/10:.4f}')
        xfit = np.linspace(np.nanmin(x[idx]), np.nanmax(x[idx]), 100)
        yfit = model.eval(params, x=xfit)
        if self.positivepeakline is not None:
            self.positivepeakline.remove()
            self.positivepeakline = None
        if self.negativepeakline is not None:
            self.negativepeakline.remove()
            self.negativepeakline = None
        if self.profilefitline is None:
            self.profilefitline = self.axes.plot(xfit, yfit, 'g-')
        else:
            self.profilefitline.set_xdata(xfit)
            self.profilefitline.set_ydata(yfit)
        self.canvas.draw_idle()
        self.center = (result.params["center"].value, result.params["center"].stderr)
        self.thickness = (result.params["outerdiameter"].value/10, result.params["outerdiameter"].stderr/10)


    @staticmethod
    def capillarytransmissionmodel(x: np.ndarray, I0: float, center: float, outerdiameter: float, wallthickness: float, sampleabsorptionlength: float, wallabsorptionlength: float, beamsigma: float, Nbeam: int):
        return I0 * capillarytransmission(x, center, outerdiameter, wallthickness, 1/sampleabsorptionlength, 1/wallabsorptionlength, beamsigma, int(Nbeam))

    @Slot()
    def fitPeak(self):
        if self.line is None:
            return
        x = self.line.get_xdata()
        y = self.line.get_ydata()
        xmin, xmax, ymin, ymax = self.axes.axis()
        idx = np.logical_and(
            np.logical_and(x >= xmin, x <= xmax),
            np.logical_and(y >= ymin, y <= ymax)
        )
        if self.sender() == self.fitNegativeToolButton:
            y = -y
        try:
            # do not use y error bars: if y<0, y**0.5 is NaN, which will break the fitting routine
            pars, covar, peakfunc = fitpeak(x[idx], y[idx], None, None, PeakType.AsymmetricLorentzian)
        except ValueError as ve:
            QtWidgets.QMessageBox.critical(self, 'Error while fitting',
                                           f'Cannot fit peak, please try another range. The error message was: {ve}')
            return
        logger.debug(f'Peak parameters: {pars}')
        logger.debug(f'Covariance matrix: {covar}')
        xfit = np.linspace(x[idx].min(), x[idx].max(), 100)
        yfit = peakfunc(xfit)
        if self.profilefitline is not None:
            self.profilefitline.remove()
            self.profilefitline = None
        if self.sender() == self.fitNegativeToolButton:
            if self.negativepeakline is None:
                self.negativepeakline = self.axes.plot(xfit, - yfit, 'b-', lw=3)[0]
            else:
                self.negativepeakline.set_xdata(xfit)
                self.negativepeakline.set_ydata(-yfit)
            self.negative = (pars[1], covar[1, 1] ** 0.5)
            self.negativeValDoubleSpinBox.blockSignals(True)
            self.negativeErrDoubleSpinBox.blockSignals(True)
            self.negativeValDoubleSpinBox.setValue(pars[1])
            self.negativeErrDoubleSpinBox.setValue(covar[1, 1] ** 0.5)
            self.negativeValDoubleSpinBox.blockSignals(False)
            self.negativeErrDoubleSpinBox.blockSignals(False)
        else:
            if self.positivepeakline is None:
                self.positivepeakline = self.axes.plot(xfit, yfit, 'r-', lw=3)[0]
            else:
                self.positivepeakline.set_xdata(xfit)
                self.positivepeakline.set_ydata(yfit)
            self.positive = (pars[1], covar[1, 1] ** 0.5)
            self.positiveValDoubleSpinBox.blockSignals(True)
            self.positiveErrDoubleSpinBox.blockSignals(True)
            self.positiveValDoubleSpinBox.setValue(pars[1])
            self.positiveErrDoubleSpinBox.setValue(covar[1, 1] ** 0.5)
            self.positiveValDoubleSpinBox.blockSignals(False)
            self.positiveErrDoubleSpinBox.blockSignals(False)
        self.canvas.draw_idle()
        self.recalculate()

    @Slot()
    def onLastScanChanged(self):
        if self.instrument.scan.firstscan() is not None:
            self.scanIndexSpinBox.setMaximum(self.instrument.scan.lastscan())
            self.scanIndexSpinBox.setMinimum(self.instrument.scan.firstscan())
            self.scanIndexSpinBox.setEnabled(True)
        else:
            self.scanIndexSpinBox.setEnabled(False)

    @Slot()
    def setValuesFromSpinboxes(self):
        self.positive = (self.positiveValDoubleSpinBox.value(), self.positiveErrDoubleSpinBox.value())
        self.negative = (self.negativeValDoubleSpinBox.value(), self.negativeErrDoubleSpinBox.value())
        self.recalculate()

    @Slot()
    def recalculate(self):
        positionval = 0.5 * (self.positive[0] + self.negative[0])
        positionerr = 0.5 * (self.positive[1] ** 2 + self.negative[1] ** 2) ** 0.5
        thicknessval = abs(self.positive[0] - self.negative[0])
        thicknesserr = (self.positive[1] ** 2 + self.negative[1] ** 2) ** 0.5
        self.center = (positionval, positionerr)
        self.thickness = (thicknessval, thicknesserr)
        self.newPositionLabel.setText(f'{positionval:.4f} \xb1 {positionerr:.4f}')
        self.newThicknessLabel.setText(f'{thicknessval:.4f} \xb1 {thicknesserr:.4f} mm')

    @Slot()
    def sampleChanged(self):
        if self.sampleNameComboBox.currentIndex() < 0:
            return
        sample = self.instrument.samplestore[self.sampleNameComboBox.currentText()]
        if self.instrument.samplestore.hasMotors() and (self.scan is not None):
            if self.instrument.samplestore.xmotorname() == self.scan.motorname:
                self.oldPositionLabel.setText(f'{sample.positionx[0]:.4f} \xb1 {sample.positionx[1]:.4f}')
            elif self.instrument.samplestore.ymotorname() == self.scan.motorname:
                self.oldPositionLabel.setText(f'{sample.positiony[0]:.4f} \xb1 {sample.positiony[1]:.4f}')
        self.oldThicknessLabel.setText(f'{sample.thickness[0] * 10.0:.4f} \xb1 {sample.thickness[1] * 10.0:.4f} mm')

    @Slot(int)
    def scanIndexChanged(self, value: int):
        self.scan = self.instrument.scan[value]
        self.signalNameComboBox.blockSignals(True)
        oldsignal = self.signalNameComboBox.currentText()
        self.signalNameComboBox.clear()
        self.signalNameComboBox.addItems(self.scan.columnnames[2:])
        self.signalNameComboBox.setCurrentIndex(self.signalNameComboBox.findText(oldsignal))
        self.signalNameComboBox.blockSignals(False)
        self.signalNameChanged()

    @Slot()
    def signalNameChanged(self):
        if self.signalNameComboBox.currentIndex() >= 0:
            self.replot()
            self.figtoolbar.update()

    @Slot()
    def replot(self):
        if self.scan is None:
            return
        if self.positivepeakline is not None:
            self.positivepeakline.remove()
            self.positivepeakline = None
        if self.negativepeakline is not None:
            self.negativepeakline.remove()
            self.negativepeakline = None
        x = self.scan[self.scan.motorname]
        y = self.scan[self.signalNameComboBox.currentText()]
        if self.derivativeToolButton.isChecked():
            y = (y[1:] - y[:-1]) / (x[1:] - x[:-1])
            x = 0.5 * (x[1:] + x[:-1])
        if self.line is None:
            self.line = self.axes.plot(x, y, 'k.-')[0]
        else:
            self.line.set_xdata(x)
            self.line.set_ydata(y)
            self.axes.relim()
            self.axes.autoscale(True)
        self.axes.set_xlabel(self.scan.motorname)
        self.axes.set_ylabel(
            'Derivative of ' + self.signalNameComboBox.currentText()
            if self.derivativeToolButton.isChecked() else self.signalNameComboBox.currentText())
        self.axes.set_title(self.scan.comment)
        self.axes.grid(True, which='both')
        self.canvas.draw_idle()

    @Slot()
    def saveCenter(self):
        positionval = 0.5 * (self.positive[0] + self.negative[0])
        positionerr = 0.5 * (self.positive[1] ** 2 + self.negative[1] ** 2) ** 0.5
        if not self.instrument.samplestore.hasMotors():
            # ask the user which direction this is
            msgbox = QtWidgets.QMessageBox(self.window())
            msgbox.setIcon(QtWidgets.QMessageBox.Question)
            msgbox.setWindowTitle('Select direction')
            msgbox.setText('Please select X or Y direction to save the determined sample center to:')
            btnX=msgbox.addButton('X', QtWidgets.QMessageBox.YesRole)
            btnY=msgbox.addButton('Y', QtWidgets.QMessageBox.NoRole)
            msgbox.addButton(QtWidgets.QMessageBox.Cancel)
            result = msgbox.exec_()
            logger.debug(f'{result=}')
            if msgbox.clickedButton() == btnX:
                xcoordinate = True
            elif msgbox.clickedButton() == btnY:
                xcoordinate = False
            else:
                xcoordinate = None
        elif self.instrument.samplestore.xmotorname() == self.scan.motorname:
            xcoordinate = True
        elif self.instrument.samplestore.ymotorname() == self.scan.motorname:
            xcoordinate = False
        else:
            xcoordinate = None
        if xcoordinate is None:
            return
        else:
            try:
                self.instrument.samplestore.updateSample(self.sampleNameComboBox.currentText(),
                                                         'positionx' if xcoordinate else 'positiony',
                                                         (positionval, positionerr))
                logger.info(
                    f'Updated {"X" if xcoordinate else "Y"} '
                    f'position of sample {self.sampleNameComboBox.currentText()} to {positionval:.4f} \xb1 {positionerr:.4f}.')
            except ValueError:
                QtWidgets.QMessageBox.critical(
                    self, 'Parameter locked',
                    f'Cannot set position for sample {self.sampleNameComboBox.currentText()}: this parameter has been set read-only!')
        self.sampleChanged()

    @Slot()
    def saveThickness(self):
        thicknessval = abs(self.positive[0] - self.negative[0])
        thicknesserr = (self.positive[1] ** 2 + self.negative[1] ** 2) ** 0.5
        sample = self.instrument.samplestore[self.sampleNameComboBox.currentText()]
        try:
            sample.thickness = (thicknessval / 10, thicknesserr / 10)
        except ValueError:
            QtWidgets.QMessageBox.critical(
                self, 'Parameter locked',
                f'Cannot set thickness for sample {sample.title}: this parameter has been set read-only!')
            return
        self.instrument.samplestore.updateSample(sample.title, 'thickness', sample.thickness)
        logger.info(
            f'Updated thickness of sample {sample.title} to {sample.thickness[0]:.4f} \xb1 {sample.thickness[1]:.4f} cm.')
        self.sampleChanged()
