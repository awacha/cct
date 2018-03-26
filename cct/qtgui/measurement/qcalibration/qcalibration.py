import logging
import os

import matplotlib.colors
import numpy as np
from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure
from sastool.misc.errorvalue import ErrorValue

from .calibrationmodel import CalibrationModel
from .peakmodel import PeakModel
from .qcalibration_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.commands.detector import Expose
from ....core.commands.motor import SetSample
from ....core.commands.xray_source import Shutter
from ....core.instrument.instrument import Instrument
from ....core.services.filesequence import FileSequence
from ....core.services.interpreter import Interpreter
from ....core.services.samples import SampleStore
from ....core.utils.inhibitor import Inhibitor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class QCalibration(QtWidgets.QWidget, Ui_Form, ToolWindow):
    # required_devices = ['pilatus', 'genix']
    # required_privilege = PRIV_MOVEMOTORS

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._failed = False
        self._updating = Inhibitor()
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        assert isinstance(self.credo, Instrument)
        self.browseMaskPushButton.clicked.connect(self.onBrowseForMask)
        self.exposePushButton.clicked.connect(self.onStartExposure)
        self.reloadExposuresPushButton.clicked.connect(self.onReloadExposures)
        self.updateMeasurementsPushButton.clicked.connect(self.onUpdateResults)
        self.updateShiftsPushButton.clicked.connect(self.onUpdateShifts)
        self.removeSelectedExposurePushButton.clicked.connect(self.onRemoveSelectedExposure)
        self.refineBeamCenterPushButton.clicked.connect(self.onRefineBeamCenter)
        self.progressBar.setVisible(False)
        self.exposureModel = CalibrationModel(
            ErrorValue(
                self.credo.config['geometry']['pixelsize'],
                self.credo.config['geometry']['pixelsize.err']),
            ErrorValue(
                self.credo.config['geometry']['wavelength'],
                self.credo.config['geometry']['wavelength.err'])
        )
        self.exposuresTreeView.setModel(self.exposureModel)
        self.figureExposure = Figure()
        self.canvasExposure = FigureCanvasQTAgg(self.figureExposure)
        self.exposureTab.setLayout(QtWidgets.QVBoxLayout())
        self.exposureTab.layout().addWidget(self.canvasExposure)
        self.toolbarExposure = NavigationToolbar2QT(self.canvasExposure, self.exposureTab)
        self.exposureTab.layout().addWidget(self.toolbarExposure)
        self.figureBeamPos = Figure()
        self.canvasBeamPos = FigureCanvasQTAgg(self.figureBeamPos)
        self.beamPosTab.setLayout(QtWidgets.QVBoxLayout())
        self.beamPosTab.layout().addWidget(self.canvasBeamPos)
        self.toolbarBeamPos = NavigationToolbar2QT(self.canvasBeamPos, self.beamPosTab)
        self.beamPosTab.layout().addWidget(self.toolbarBeamPos)
        self.figureCurves = Figure()
        self.canvasCurves = FigureCanvasQTAgg(self.figureCurves)
        self.curvesTab.setLayout(QtWidgets.QVBoxLayout())
        self.curvesTab.layout().addWidget(self.canvasCurves)
        self.toolbarCurves = NavigationToolbar2QT(self.canvasCurves, self.curvesTab)
        self.curvesTab.layout().addWidget(self.toolbarCurves)
        self.figureCalibration = Figure()
        self.canvasCalibration = FigureCanvasQTAgg(self.figureCalibration)
        self.calibrationTab.setLayout(QtWidgets.QVBoxLayout())
        self.calibrationTab.layout().addWidget(self.canvasCalibration)
        self.toolbarCalibration = NavigationToolbar2QT(self.canvasCalibration, self.calibrationTab)
        self.calibrationTab.layout().addWidget(self.toolbarCalibration)
        self.exposuresTreeView.selectionModel().selectionChanged.connect(self.onExposureSelectionChanged)
        sam = self.credo.services['samplestore']
        assert isinstance(sam, SampleStore)
        self.onSampleListChanged(sam)
        self.peaksModel=PeakModel()
        self.peaksModel.calibrationChanged.connect(self.onPeakModelCalibrationChanged)
        self.peaksTreeView.setModel(self.peaksModel)

    def onExposureSelectionChanged(self):
        try:
            index = self.exposuresTreeView.selectedIndexes()[0]
        except IndexError:
            self.figureExposure.clear()
            self.canvasExposure.draw()
            self.removeSelectedExposurePushButton.setEnabled(False)
            return
        assert isinstance(index, QtCore.QModelIndex)
        self.removeSelectedExposurePushButton.setEnabled(True)
        ex = self.exposureModel.exposure(index)
        self.figureExposure.clear()
        ax = self.figureExposure.add_subplot(1, 1, 1)
        ex.imshow(norm=matplotlib.colors.LogNorm(), axes=ax)
        self.figureExposure.tight_layout()
        self.canvasExposure.draw()

    def onSampleListChanged(self, sam: SampleStore):
        with self._updating:
            currenttext = self.sampleComboBox.currentText()
            self.sampleComboBox.clear()
            self.sampleComboBox.addItems(sorted([s.title for s in sam.get_samples()]))
            idx = self.sampleComboBox.findText(currenttext)
            if idx < 0:
                idx = 0
            self.sampleComboBox.setCurrentIndex(idx)

    def drawBeamPos(self):
        self.figureBeamPos.clear()
        bcx = self.exposureModel.beamposxs()
        bcy = self.exposureModel.beamposys()
        shifts = self.exposureModel.shifts()
        ax = self.figureBeamPos.add_subplot(1, 1, 1)
        ax.plot(shifts, bcx, 'bs')
        ax.set_xlabel('Shift (mm)')
        ax.set_ylabel('Horizontal beam position (pixel)', color='b')
        ax1 = ax.twinx()
        ax1.plot(shifts, bcy, 'ro')
        ax1.set_ylabel('Vertical beam position (pixel)', color='r')
        self.figureBeamPos.tight_layout()
        self.canvasBeamPos.draw()

    def onUpdateShifts(self):
        self.exposureModel.updateShifts(
            ErrorValue(self.shiftValueDoubleSpinBox.value(), self.shiftErrorDoubleSpinBox.value()))
        self.drawPeaks()
        self.drawBeamPos()
        self.drawCurves()

    def onRemoveSelectedExposure(self):
        self.exposureModel.removeRow(self.exposuresTreeView.selectedIndexes()[0].row(), None)

    def onRefineBeamCenter(self):
        self.exposureModel.refineBeamCenter()

    def loadExposure(self, fsn: int, totalshift: ErrorValue):
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        try:
            ex = fs.load_exposure(self.credo.config['path']['prefixes']['tst'], fsn)
        except FileNotFoundError:
            logger.debug('Skipped loading of unavailable exposure: prefix {}, fsn {}.'.format(
                self.credo.config['path']['prefixes']['tst'], fsn
            ))
            return
        if self.overrideMaskCheckBox.isChecked():
            ex.mask = fs.get_mask(self.maskFileLineEdit.text())
        logger.debug('Adding exposure {}'.format(fsn))
        self.exposureModel.addExposure(fsn, ex, totalshift, True, self.peakPointsBeforeAndAfterSpinBox.value())
        logger.debug('Added exposure {}'.format(fsn))

    def onReloadExposures(self):
        shift = ErrorValue(self.shiftValueDoubleSpinBox.value(), self.shiftErrorDoubleSpinBox.value())
        self.exposureModel.clear()
        for i, f in enumerate(range(self.firstFSNSpinBox.value(), self.lastFSNSpinBox.value() + 1)):
            self.loadExposure(f, i * shift)
        self.drawPeaks()
        self.drawCurves()
        self.drawBeamPos()

    def drawPeaks(self):
        self.figureCalibration.clear()
        ax = self.figureCalibration.add_subplot(1, 1, 1)
        for peakclass in range(self.exposureModel.peakClassesCount()):
            shifts = self.exposureModel.shifts()
            dshifts = self.exposureModel.dshifts()
            peaks = self.exposureModel.peaks(peakclass)
            dpeaks = self.exposureModel.dpeaks(peakclass)
            valid = np.logical_and(np.isfinite(shifts), np.isfinite(peaks))
            shifts = shifts[valid]
            dshifts = dshifts[valid]
            peaks = peaks[valid]
            dpeaks = dpeaks[valid]
            x = np.linspace(shifts.min() - shifts.ptp() / len(shifts), shifts.max() + shifts.ptp() / len(shifts), 100)
            line = ax.errorbar(shifts, peaks, dpeaks, dshifts, 'o')[0]
            try:
                poly = np.polyfit(shifts, peaks, 1)
                ax.plot(x, poly[0] * x + poly[1], '--', color=line.get_color())
            except ValueError:
                # do not draw fit lines if we have only one point
                pass
        ax.set_xlabel('Shift (mm)')
        ax.set_ylabel('Peak position (pixel)')
        self.figureCalibration.tight_layout()
        self.canvasCalibration.draw()

    def drawCurves(self, factor=5):
        self.figureCurves.clear()
        ax = self.figureCurves.add_subplot(1, 1, 1)
        for i in range(self.exposureModel.rowCount()):
            curve = self.exposureModel.curve(i) * factor ** i
            line = curve.loglog(axes=ax)[0]
            for peakclass in range(self.exposureModel.peakClassesCount()):
                peak = self.exposureModel.peaks(peakclass)[i]
                value = np.interp(peak, curve.q, curve.Intensity)
                ax.plot([peak], [value], 'o', color=line.get_color())
        ax.set_xlabel('q (nm$^{-1}$)')
        ax.set_ylabel('Intensity')
        self.canvasCurves.draw()

    def onUpdateResults(self):
        alpha = self.exposureModel.alpha(None)
        alphax = self.exposureModel.alphax()
        alphay = self.exposureModel.alphay()
        self.alphaLabel.setText('{0.val:.2f} \xb1 {0.err:.2f} mrad ({1.val:.2f} \xb1 {1.err:.2f}°)'.format(
            1000 * alpha, alpha * 180 / np.pi))
        self.alphaXLabel.setText('{0.val:.2f} \xb1 {0.err:.2f} mrad ({1.val:.2f} \xb1 {1.err:.2f}°)'.format(
            1000 * alphax, alphax * 180 / np.pi))
        self.alphaYLabel.setText('{0.val:.2f} \xb1 {0.err:.2f} mrad ({1.val:.2f} \xb1 {1.err:.2f}°)'.format(
            1000 * alphay, alphay * 180 / np.pi))
        self.updatePeakData()

    def onPeakModelCalibrationChanged(self):
        par, stat=self.peaksModel.fitLatticeParameter()
        self.latticeParameterLabel.setText('{0.val:.4f} \xb1 {0.err:.4f} nm'.format(par))

    def updatePeakData(self):
        self.peaksModel.calibrationChanged.disconnect()
        self.peaksModel=PeakModel()
        self.peaksTreeView.setModel(self.peaksModel)
        self.peaksModel.calibrationChanged.connect(self.onPeakModelCalibrationChanged)
        for pi in range(self.exposureModel.peakClassesCount()):
            try:
                q,dist0=self.exposureModel.calibrate(pi)
            except ValueError:
                continue
            self.peaksModel.addPeak(q, dist0)
        for c in range(self.peaksModel.columnCount()):
            self.peaksTreeView.resizeColumnToContents(c)


    def onBrowseForMask(self):
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        filename, fltr = QtWidgets.QFileDialog.getOpenFileName(
            self,
            'Load mask file',
            directory=os.path.join(os.getcwd(), self.credo.config['path']['directories']['mask']),
            filter='Mask files (*.mat);;All files (*)',
            initialFilter='Mask files (*.mat)'
        )
        if not filename:
            return
        else:
            self.maskFileLineEdit.setText(os.path.normpath(filename))

    def onStartExposure(self):
        if self.isBusy():
            self.credo.services['interpreter'].kill()
            return
        else:
            self.setBusy()
            if self.sampleCheckBox.isChecked():
                self.executeCommand(SetSample, self.sampleComboBox.currentText())
            else:
                self.onCmdReturn(self.credo.services['interpreter'], SetSample.name, True)

    def onCmdFail(self, interpreter: Interpreter, cmdname: str, exception: Exception, traceback: str):
        self._failed = cmdname

    def onCmdReturn(self, interpreter: Interpreter, cmdname: str, retval):
        super().onCmdReturn(interpreter, cmdname, retval)
        if self._failed == SetSample.name:
            self.setIdle()
            return
        elif self._failed == Shutter.name:
            self.setIdle()
            return
        elif self._failed == Expose.name:
            # exposure broken. close shutter if needed
            if self.autoShutterCheckBox.isChecked():
                self.executeCommand(Shutter, False)
                return
            else:
                self.onCmdReturn(interpreter, Shutter.name, False)
                return
        elif self._failed:
            raise ValueError(self._failed)

        if cmdname == SetSample.name:
            # sample is in the beam. Open the shutter if needed.
            if self.autoShutterCheckBox.isChecked():
                self.executeCommand(Shutter, True)
                return
            else:
                self.onCmdReturn(interpreter, Shutter.name, True)
                return
        elif cmdname == Shutter.name and retval:
            # shutter is open. Start the exposure
            self.executeCommand(Expose, self.exposureTimeDoubleSpinBox.value(),
                                self.credo.config['path']['prefixes']['tst'])
            return
        elif cmdname == Expose.name:
            if self.autoShutterCheckBox.isChecked():
                self.executeCommand(Shutter, False)
                return
            else:
                self.onCmdReturn(interpreter, Shutter.name, False)
                return
        elif cmdname == Shutter.name and not retval:
            # load the exposure and add to the model
            if not self._failed:
                fsn = self.credo.services['filesequence'].get_lastfsn(self.credo.config['path']['prefixes']['tst'])
                shiftcnt = self.exposureModel.rowCount()
                self.loadExposure(fsn, ErrorValue(self.shiftValueDoubleSpinBox.value(),
                                                  self.shiftErrorDoubleSpinBox.value()) * shiftcnt)
                self.lastFSNSpinBox.setValue(fsn)
                self.firstFSNSpinBox.setValue(self.exposureModel.fsn(0))
                self.drawCurves()
                self.drawBeamPos()
                self.drawPeaks()
            self.setIdle()
            return

    def setIdle(self):
        super().setIdle()
        self._failed = False
        self.exposePushButton.setText('Expose')
        for w in [
            self.exposuresGroupBox,
            self.sampleComboBox,
            self.sampleCheckBox,
            self.exposureTimeDoubleSpinBox,
            self.autoShutterCheckBox
        ]:
            w.setEnabled(True)

    def setBusy(self):
        super().setBusy()
        self.exposePushButton.setText('Stop exposure')
        for w in [
            self.exposuresGroupBox,
            self.sampleComboBox,
            self.sampleCheckBox,
            self.exposureTimeDoubleSpinBox,
            self.autoShutterCheckBox
        ]:
            w.setEnabled(False)
