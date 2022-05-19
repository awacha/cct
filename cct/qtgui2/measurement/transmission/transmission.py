import logging

from PyQt5 import QtWidgets, QtCore, QtGui

from .transmission_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.devices import DeviceType

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class TransmissionUi(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicetypes = [DeviceType.Source, DeviceType.Detector]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.transmissionTreeView.setModel(self.instrument.transmission)
        self.sampleListView.setModel(self.instrument.samplestore.sortedmodel)
        self.addSamplesPushButton.clicked.connect(self.onAddSamplesClicked)
        self.removeSamplesPushButton.clicked.connect(self.onRemoveSamplesClicked)
        self.clearSampleListPushButton.clicked.connect(self.onClearTransmissionList)
        self.emptySampleComboBox.setModel(self.instrument.samplestore.sortedmodel)
        self.emptySampleComboBox.setModelColumn(0)
        self.startStopPushButton.clicked.connect(self.onStartStopClicked)
        self.sortSamplesByNamePushButton.clicked.connect(self.sortSamplesByName)
        self.sortSamplesByMotorMovementPushButton.clicked.connect(self.sortSamplesForMinimumMotorMovement)
        self.progressBar.setVisible(False)
        self.instrument.transmission.started.connect(self.onTransmissionStarted)
        self.instrument.transmission.finished.connect(self.onTransmissionFinished)
        self.instrument.transmission.progress.connect(self.onTransmissionProgress)
        self.instrument.transmission.sampleStarted.connect(self.onTransmissionSampleStarted)
        self.oldstyleCheckBox.toggled.connect(self.errorPropagationModeChanged)
        self.saveResultsPushButton.clicked.connect(self.forceSaveResults)
        self.resize(self.minimumSize())

    def forceSaveResults(self):
        self.instrument.transmission.saveAllResults()

    def errorPropagationModeChanged(self, checked: bool):
        self.instrument.transmission.setErrorPropagationMode(not checked)

    def onAddSamplesClicked(self):
        samples = [index.data(QtCore.Qt.DisplayRole) for index in self.sampleListView.selectedIndexes()]
        if not samples:
            return
        logger.debug(samples)
        for sample in samples:
            try:
                self.instrument.transmission.addSample(sample)
            except RuntimeError:
                pass
        self.sampleListView.selectionModel().clearSelection()

    def onRemoveSamplesClicked(self):
        samplenames = [index.data(QtCore.Qt.DisplayRole) for index in
                       self.transmissionTreeView.selectionModel().selectedRows(0)]
        for samplename in samplenames:
            self.instrument.transmission.removeSample(samplename)

    def onClearTransmissionList(self):
        self.instrument.transmission.clear()

    def onTransmissionStarted(self):
        self.setBusy()
        for widget in [self.emptySampleComboBox, self.nImagesSpinBox, self.exposureTimeDoubleSpinBox,
                       self.exposureDelayDoubleSpinBox, self.lazyCheckBox, self.sampleListView,
                       self.addSamplesPushButton, self.removeSamplesPushButton,
                       self.clearSampleListPushButton, self.sortSamplesByMotorMovementPushButton,
                       self.sortSamplesByNamePushButton]:
            widget.setEnabled(False)
        self.startStopPushButton.setEnabled(True)
        self.startStopPushButton.setText('Stop')
        self.startStopPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/stop.svg')))
        self.progressBar.setVisible(True)

    def onTransmissionFinished(self, success: bool, message: str):
        if not success:
            QtWidgets.QMessageBox.critical(self, 'Transmission stopped', message)
        for widget in [self.emptySampleComboBox, self.nImagesSpinBox, self.exposureTimeDoubleSpinBox,
                       self.exposureDelayDoubleSpinBox, self.lazyCheckBox, self.sampleListView,
                       self.addSamplesPushButton, self.removeSamplesPushButton,
                       self.clearSampleListPushButton, self.sortSamplesByMotorMovementPushButton,
                       self.sortSamplesByNamePushButton]:
            widget.setEnabled(True)
        self.startStopPushButton.setEnabled(True)
        self.startStopPushButton.setText('Start')
        self.startStopPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
        self.progressBar.setVisible(False)
        self.setIdle()

    def onTransmissionSampleStarted(self, samplename: str, sampleindex: int, nsamples: int):
        pass

    def onTransmissionProgress(self, start: float, end: float, current: float, message: str):
        self.progressBar.setTextVisible(True)
        self.progressBar.setFormat(message)
        if start == end:
            self.progressBar.setRange(0,0)
        else:
            self.progressBar.setRange(0, 1000)
            self.progressBar.setValue(int(1000*(current-start)/(end-start)))

    def onStartStopClicked(self):
        if self.startStopPushButton.text() == 'Start':
            self.instrument.transmission.startMeasurement(
                self.emptySampleComboBox.currentText(), self.exposureTimeDoubleSpinBox.value(),
                self.nImagesSpinBox.value(), self.exposureDelayDoubleSpinBox.value(), self.lazyCheckBox.isChecked())
        elif self.startStopPushButton.text() == 'Stop':
            self.instrument.transmission.stopMeasurement()
        else:
            assert False

    def sortSamplesByName(self):
        self.instrument.transmission.orderSamplesByName()

    def sortSamplesForMinimumMotorMovement(self):
        self.instrument.transmission.emptysample = self.emptySampleComboBox.currentText()
        self.instrument.transmission.orderSamplesForLeastMovement()
