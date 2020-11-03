import enum
import logging

from PyQt5 import QtWidgets, QtGui
from .simpleexposure_ui import Ui_Form
from ...utils.window import WindowRequiresDevices

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class State(enum.Enum):
    Idle = enum.auto()
    MovingSample = enum.auto()
    OpeningShutter = enum.auto()
    Exposing = enum.auto()
    ClosingShutter = enum.auto()
    StopRequested = enum.auto()
    WaitingForImages = enum.auto()


class SimpleExposure(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    """Steps of the measurement:

    1. move to sample (if needed)
    2. open shutter (if needed)
    3. expose
    4. close shutter (if needed)
    5. collect outstanding images

    If an error happens in step..
        1: jump to 5
        2: jump to 5
        3: jump to 4
        4: jump to 5
    """

    required_devicetypes = ['detector']
    state: State = State.Idle
    imagesrequired: int=0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.imageCountSpinBox.valueChanged.connect(self.onImageCountValueChanged)
        self.startStopPushButton.clicked.connect(self.onStartStopClicked)
        self.instrument.samplestore.sampleListChanged.connect(self.repopulateSampleComboBox)
        self.repopulateSampleComboBox()
        self.prefixComboBox.clear()
        self.prefixComboBox.addItems(sorted(self.instrument.io.prefixes))
        self.progressBar.hide()
        self.resize(self.minimumSizeHint())
        self.setUiEnabled()

    def onImageCountValueChanged(self, value: int):
        self.delayDoubleSpinBox.setEnabled(value > 1)

    # Steps of the measurement

    def _movesample(self):
        logger.debug('Moving sample')
        if self.state == State.StopRequested:
            logger.debug('No, not moving sample: stop requested.')
            self._waitforimages()
            return
        if self.sampleNameCheckBox.isChecked():
            self.instrument.samplestore.movingToSample.connect(self.onMovingToSample)
            self.instrument.samplestore.movingFinished.connect(self.onMovingToSampleFinished)
            self.instrument.samplestore.moveToSample(self.sampleNameComboBox.currentText())
            self.state = State.MovingSample
        else:
            logger.debug('No, not moving sample, opening shutter.')
            self._openshutter()

    def _openshutter(self):
        self.progressBar.setRange(0, 0)
        self.progressBar.setFormat('Opening shutter')
        self.progressBar.show()
        logger.debug('Opening shutter')
        if self.state == State.StopRequested:
            logger.debug('No, not opening shutter: stop requested')
            self._waitforimages()
            return
        if self.shutterCheckBox.isChecked():
            self.instrument.devicemanager.source().shutter.connect(self.onShutterChanged)
            self.instrument.devicemanager.source().moveShutter(True)
            self.state = State.OpeningShutter
        else:
            logger.debug('No, not opening shutter, starting the exposure')
            self._startexposure()

    def _closeshutter(self):
        self.progressBar.setRange(0, 0)
        self.progressBar.setFormat('Closing shutter')
        self.progressBar.show()
        logger.debug('Closing shutter')
        if self.state == State.StopRequested:
            logger.debug('No, not closing shutter: stop requested')
            self._waitforimages()
            return
        if self.shutterCheckBox.isChecked():
            self.instrument.devicemanager.source().shutter.connect(self.onShutterChanged)
            self.instrument.devicemanager.source().moveShutter(False)
            self.state = State.ClosingShutter
        else:
            logger.debug('No, not closing shutter, finishing')
            self._waitforimages()

    def _waitforimages(self):
        self.state = State.WaitingForImages
        self.progressBar.setRange(0, 0)
        self.progressBar.setFormat('Waiting for images')
        self.progressBar.show()
        if self.imagesrequired == 0:
            self.cleanupAfterExposure()

    def _startexposure(self):
        logger.debug('Starting the exposure')
        if self.state == State.StopRequested:
            logger.debug('No, not starting exposure: stop requested')
            self._waitforimages()
            return
        self.instrument.exposer.exposureFinished.connect(self.onExposureFinished)
        self.instrument.exposer.imageReceived.connect(self.onImageReceived)
        self.instrument.exposer.exposureProgress.connect(self.onExposureProgress)
        self.instrument.exposer.startExposure(self.prefixComboBox.currentText(), self.exposureTimeDoubleSpinBox.value(), self.imageCountSpinBox.value(), self.delayDoubleSpinBox.value())
        self.imagesrequired = self.imageCountSpinBox.value()
        self.state = State.Exposing

    # slots for checking the results of the steps

    def onShutterChanged(self, state: bool):
        assert self.state in [State.OpeningShutter, State.ClosingShutter]
        self.instrument.devicemanager.source().shutter.disconnect(self.onShutterChanged)

        if self.state == State.OpeningShutter:
            if state:
                # successfully opened shutter
                self._startexposure()
            else:
                # error, cannot open shutter
                QtWidgets.QMessageBox.critical(self, 'Error', 'Cannot open shutter.')
                self._waitforimages()
        elif self.state == State.ClosingShutter:
            if state:
                # could not close shutter. This should not happen but who knows...
                QtWidgets.QMessageBox.critical(self, 'Error', 'Cannot close shutter')
                self._waitforimages()
            else:
                self._waitforimages()
        else:
            assert False

    def onMovingToSample(self, samplename:str, motorname: str, current:float, start:float, end):
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue((current-start)/(end-start) * 100)
        self.progressBar.setFormat(f'Moving {motorname}: {current:.3f}')
        self.progressBar.setVisible(True)

    def onMovingToSampleFinished(self, samplename: str, success: bool):
        assert self.state == State.MovingSample
        self.instrument.samplestore.movingToSample.disconnect(self.onMovingToSample)
        self.instrument.samplestore.movingFinished.disconnect(self.onMovingToSampleFinished)
        if success:
            self._openshutter()
        else:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Sample {samplename} could not be moved into the beam.')
            self._waitforimages()

    def onExposureFinished(self, success: bool):
        self.instrument.exposer.exposureFinished.disconnect(self.onExposureFinished)
        self.instrument.exposer.exposureProgress.disconnect(self.onExposureProgress)
        self._waitforimages()

    def onImageReceived(self, exposure):
        self.imagesrequired -= 1
        self.mainwindow.showPattern(exposure)
        if self.imagesrequired == 0:
            # we are not waiting for any more images:
            self.instrument.exposer.imageReceived.disconnect(self.onImageReceived)
            if self.state == State.WaitingForImages:
                self.cleanupAfterExposure()

    def onExposureProgress(self, prefix, fsn, currenttime, starttime, endtime):
        self.progressBar.setVisible(True)
        self.progressBar.setRange(starttime*100, endtime*100)
        self.progressBar.setValue(currenttime*100)
        self.progressBar.setFormat(f'Exposing {prefix} #{fsn}, {endtime-currenttime:.2} secs remaining')

    def onStartStopClicked(self):
        if self.startStopPushButton.text() == 'Start':
            self.setBusy()
            # start an exposure: first move the sample, then open the shutter, then expose.
            self.startStopPushButton.setText('Stop')
            self.startStopPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/stop.svg")))
            self.setUiEnabled()
            self._movesample()
        elif self.startStopPushButton.text() == 'Stop':
            # stop an exposure
            if self.state == State.Exposing:
                self.instrument.exposer.stopExposure()
            elif self.state == State.MovingSample:
                self.instrument.samplestore.stopMotors()
            elif self.state == State.OpeningShutter:
                pass
            self.state = State.StopRequested

    def repopulateSampleComboBox(self):
        current = self.sampleNameComboBox.currentText()
        self.sampleNameComboBox.clear()
        if not list(self.instrument.samplestore):
            self.sampleNameCheckBox.setChecked(False)
            self.sampleNameCheckBox.setEnabled(False)
            return
        else:
            self.sampleNameComboBox.setEnabled(True)
        self.sampleNameComboBox.addItems(sorted([s.title for s in self.instrument.samplestore]))
        self.sampleNameComboBox.setCurrentIndex(self.sampleNameComboBox.findText(current))
        if (self.sampleNameComboBox.currentIndex() < 0) and (self.instrument.samplestore.currentSample() is not None):
            self.sampleNameComboBox.setCurrentIndex(
                self.sampleNameComboBox.findText(self.instrument.samplestore.currentSample().title))

    def cleanupAfterExposure(self):
        self.state = State.Idle
        self.setIdle()
        self.progressBar.setVisible(False)
        self.startStopPushButton.setText('Start')
        self.startStopPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/exposure.svg")))
        self.setUiEnabled()

    def setUiEnabled(self):
        for widget in [self.sampleNameComboBox, self.sampleNameCheckBox, self.prefixComboBox, self.exposureTimeDoubleSpinBox, self.delayDoubleSpinBox, self.imageCountSpinBox, self.shutterCheckBox]:
            widget.setEnabled(self.isIdle())
