import enum
from typing import Optional, Tuple
import logging

from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import pyqtSlot as Slot

from .scan_ui import Ui_Form
from ...utils.plotscan import PlotScan
from ...utils.window import WindowRequiresDevices
from ....core2.devices import DeviceType

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class RangeType(enum.Enum):
    Absolute = 'Absolute'
    Relative = 'Relative'
    SymmetricRelative = 'Symmetric'


class ScanMeasurement(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicetypes = [DeviceType.Source, DeviceType.Detector]
    motorname: Optional[str] = None
    scangraph: Optional[PlotScan] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.motorComboBox.addItems(sorted([m.name for m in self.instrument.motors.motors]))
        self.motorComboBox.currentIndexChanged.connect(self.onMotorChanged)
        self.motorComboBox.setCurrentIndex(-1)
        self.rangeTypeComboBox.addItems([rt.value for rt in RangeType])
        self.rangeTypeComboBox.currentIndexChanged.connect(self.onRangeTypeSelected)
        for widget in [self.rangeTypeComboBox, self.rangeMinDoubleSpinBox, self.rangeMaxDoubleSpinBox,
                       self.stepSizeDoubleSpinBox, self.stepCountSpinBox, self.countingTimeDoubleSpinBox,
                       self.commentLineEdit]:
            widget.setEnabled(False)
        self.rangeTypeComboBox.setEnabled(False)
        self.rangeMaxDoubleSpinBox.setEnabled(False)
        self.progressBar.hide()
        self.rangeMinDoubleSpinBox.valueChanged.connect(self.onRangeChanged)
        self.rangeMaxDoubleSpinBox.valueChanged.connect(self.onRangeChanged)
        self.stepCountSpinBox.valueChanged.connect(self.onStepsChanged)
        self.stepSizeDoubleSpinBox.valueChanged.connect(self.onStepsChanged)
        self.commentLineEdit.textChanged.connect(self.onCommentChanged)
        self.startStopPushButton.clicked.connect(self.onStartStopClicked)
        self.shrinkWindow()

    @Slot()
    def onRangeTypeSelected(self):
        if self.rangeTypeComboBox.currentIndex() < 0:
            return
        rt = RangeType(self.rangeTypeComboBox.currentText())
        self.fromLabel.setText('Half width:' if rt == RangeType.SymmetricRelative else 'From:')
        if rt == RangeType.SymmetricRelative:
            self.toLabel.hide()
            self.rangeMaxDoubleSpinBox.hide()
        else:
            self.toLabel.show()
            self.rangeMaxDoubleSpinBox.show()
        #self.toLabel.setVisible(False if rt == RangeType.SymmetricRelative else True)
        #self.rangeMaxDoubleSpinBox.setVisible(False if rt == RangeType.SymmetricRelative else True)
        if self.motorname is not None:
            self.onMotorPositionChanged(self.instrument.motors[self.motorname].where())
        self.shrinkWindow()

    def shrinkWindow(self):
        self.resize(self.minimumSizeHint())

    @Slot()
    def onMotorChanged(self):
        if self.motorname is not None:
            self.disconnectMotor(self.instrument.motors[self.motorname])
            self.motorname = None
        if self.motorComboBox.currentIndex() < 0:
            return
        self.motorname = self.motorComboBox.currentText()
        self.connectMotor(self.instrument.motors[self.motorname])
        self.onMotorPositionChanged(self.instrument.motors[self.motorname].where())
        for widget in [self.rangeTypeComboBox, self.rangeMinDoubleSpinBox, self.rangeMaxDoubleSpinBox,
                       self.stepSizeDoubleSpinBox, self.stepCountSpinBox, self.countingTimeDoubleSpinBox,
                       self.commentLineEdit]:
            widget.setEnabled(True)

    @Slot(float)
    def onMotorPositionChanged(self, newposition: float):
        if self.startStopPushButton.text() != 'Start':
            # scan is running, do not update motor limits in the input boxes
            return
        rt = RangeType(self.rangeTypeComboBox.currentText())
        motor = self.instrument.motors[self.motorname]
        if rt == RangeType.Absolute:
            self.rangeMinDoubleSpinBox.setRange(motor['softleft'], motor['softright'])
            self.rangeMaxDoubleSpinBox.setRange(motor['softleft'], motor['softright'])
        elif rt == RangeType.Relative:
            self.rangeMinDoubleSpinBox.setRange(motor['softleft'] - newposition, motor['softright'] - newposition)
            self.rangeMaxDoubleSpinBox.setRange(motor['softleft'] - newposition, motor['softright'] - newposition)
        elif rt == RangeType.SymmetricRelative:
            radius = min(abs(motor['softleft'] - newposition), abs(motor['softright'] - newposition))
            self.rangeMinDoubleSpinBox.setRange(0, radius)
            self.rangeMaxDoubleSpinBox.setRange(0, radius)

    @Slot()
    def onRangeChanged(self):
        self.onStepsChanged()

    @Slot()
    def onStepsChanged(self):
        rt = RangeType(self.rangeTypeComboBox.currentText())
        length = (self.rangeMinDoubleSpinBox.value() * 2) if rt == RangeType.SymmetricRelative else (
                self.rangeMaxDoubleSpinBox.value() - self.rangeMinDoubleSpinBox.value())
        if self.sender() is self.stepCountSpinBox:
            stepsize = length / (self.stepCountSpinBox.value() - 1)
            self.stepSizeDoubleSpinBox.blockSignals(True)
            self.stepSizeDoubleSpinBox.setValue(stepsize)
            self.stepSizeDoubleSpinBox.blockSignals(False)
        else:
            if self.stepSizeDoubleSpinBox.value() == 0:
                self.stepSizeDoubleSpinBox.setValue(0.1)
            stepcount = max(1, abs(int(length / self.stepSizeDoubleSpinBox.value()))) + 1
            # do not monkey around with blocksignals: stepcount is the definitive
            self.stepCountSpinBox.setValue(stepcount)

    @Slot()
    def onCommentChanged(self):
        self.startStopPushButton.setEnabled(bool(self.commentLineEdit.text()))

    @Slot()
    def onStartStopClicked(self):
        if self.startStopPushButton.text() == 'Start':
            rt = RangeType(self.rangeTypeComboBox.currentText())
            if rt == RangeType.Absolute:
                rangemin, rangemax = self.rangeMinDoubleSpinBox.value(), self.rangeMaxDoubleSpinBox.value()
                relative = False
            elif rt == RangeType.Relative:
                rangemin, rangemax = self.rangeMinDoubleSpinBox.value(), self.rangeMaxDoubleSpinBox.value()
                relative = True
            elif rt == RangeType.SymmetricRelative:
                rangemin, rangemax = -self.rangeMinDoubleSpinBox.value(), self.rangeMinDoubleSpinBox.value()
                relative = True
            else:
                assert False
            self.instrument.scan.scanstarted.connect(self.onScanStarted)
            self.instrument.scan.scanfinished.connect(self.onScanEnded)
            self.instrument.scan.scanpointreceived.connect(self.onScanPointReceived)
            self.instrument.scan.scanprogress.connect(self.onScanProgress)
            self.startStopPushButton.setEnabled(False)
            self.instrument.scan.startScan(self.motorname, rangemin, rangemax, self.stepCountSpinBox.value(), relative,
                                           self.countingTimeDoubleSpinBox.value(), self.commentLineEdit.text(),
                                           self.resetMotorCheckBox.isChecked(), self.shutterCheckBox.isChecked())
        else:
            self.startStopPushButton.setEnabled(False)
            self.instrument.scan.stopScan()

    @Slot(int)
    def onScanStarted(self, scanindex: int):
        logger.debug('onScanStarted')
        for widget in [self.motorComboBox, self.rangeTypeComboBox, self.rangeMinDoubleSpinBox,
                       self.rangeMaxDoubleSpinBox, self.stepCountSpinBox, self.stepSizeDoubleSpinBox,
                       self.countingTimeDoubleSpinBox, self.commentLineEdit, self.shutterCheckBox,
                       self.resetMotorCheckBox]:
            widget.setEnabled(False)
        self.setBusy()
        self.startStopPushButton.setEnabled(True)
        self.startStopPushButton.setText('Stop')
        self.startStopPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/stop.svg")))
        self.scangraph = None
        self.progressBar.show()
        self.progressBar.setRange(0, 0)
        self.progressBar.setFormat('Starting scan...')

    @Slot(bool, int, str)
    def onScanEnded(self, success: bool,  scanindex: int, message: str):
        for widget in [self.motorComboBox, self.rangeTypeComboBox, self.rangeMinDoubleSpinBox,
                       self.rangeMaxDoubleSpinBox, self.stepCountSpinBox, self.stepSizeDoubleSpinBox,
                       self.countingTimeDoubleSpinBox, self.commentLineEdit, self.shutterCheckBox,
                       self.resetMotorCheckBox]:
            widget.setEnabled(True)
        self.startStopPushButton.setEnabled(True)
        self.startStopPushButton.setText('Start')
        self.startStopPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/start.svg")))
        if self.scangraph is not None:
            try:
                self.scangraph.setRecording(False)
            except RuntimeError:
                # this can happen when the user closes the scan graph prematurely
                pass
            self.scangraph = None
        self.progressBar.hide()
        self.instrument.scan.scanstarted.disconnect(self.onScanStarted)
        self.instrument.scan.scanfinished.disconnect(self.onScanEnded)
        self.instrument.scan.scanpointreceived.disconnect(self.onScanPointReceived)
        self.instrument.scan.scanprogress.disconnect(self.onScanProgress)
        if not success:
            QtWidgets.QMessageBox.critical(self, "Error while scan", f"Scan ended with an error message: {message}")
        self.setIdle()
        self.shrinkWindow()

    @Slot(int, int, int, object)
    def onScanPointReceived(self, scanindex:int, currentpoint:int, maxpoints:int, readings: Tuple[float, ...]):
        if (self.scangraph is None) and (currentpoint == 0):
            self.scangraph = self.mainwindow.addSubWindow(PlotScan, singleton=False)
            assert isinstance(self.scangraph, PlotScan)
            self.scangraph.setScan(self.instrument.scan[scanindex])
            self.scangraph.setRecording(True)
        elif self.scangraph is not None:
            try:
                self.scangraph.replot()
            except RuntimeError:
                # this can happen when the user closes the scan graph during scan
                self.scangraph = None
        else:
            pass

    @Slot(float, float, float, str)
    def onScanProgress(self, start: float, end: float, current: float, message: str):
        if end == start:
            self.progressBar.setRange(0, 0)
        else:
            self.progressBar.setRange(0, 1000)
            self.progressBar.setValue(int((current - start) / (end - start) * 1000))
        self.progressBar.setFormat(message)
