from typing import Optional

import h5py
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from .h5selector_ui import Ui_Form
from ...core2.dataclasses import Exposure
from ...core2.instrument.instrument import Instrument
from ..utils.filebrowsers import getOpenFile


class H5Selector(QtWidgets.QWidget, Ui_Form):
    filename: Optional[str] = None
    datasetSelected = Signal(str, str, str)

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.distanceComboBox.setEnabled(False)
        self.sampleNameComboBox.setEnabled(False)
        self.browsePushButton.clicked.connect(self.browseH5FileName)
        self.sampleNameComboBox.currentIndexChanged.connect(self.sampleNameSelected)
        self.distanceComboBox.currentIndexChanged.connect(self.distanceSelected)

    @Slot()
    def browseH5FileName(self):
        filename = getOpenFile(
            self, "Select a HDF5 file", "", "CREDO Processed Data (*.cpt4);;HDF5 files (*.h5 *.hdf5);;All files (*)",)
        if not filename:
            return
        try:
            with h5py.File(filename, 'r', libver='latest', swmr=True) as f:
                self.sampleNameComboBox.clear()
                self.sampleNameComboBox.addItems(sorted(f['Samples']))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Cannot open H5 file",
                                           f"Error while opening H5 file {filename}: {exc}")
        else:
            self.filename = filename
            self.browsePushButton.setToolTip(f'Current file: {self.filename}')
            self.sampleNameComboBox.setEnabled(True)
            self.sampleNameSelected()

    @Slot()
    def sampleNameSelected(self):
        if (self.sampleNameComboBox.currentIndex() < 0) or (self.filename is None):
            self.distanceComboBox.clear()
            self.distanceComboBox.setEnabled(False)
            return
        try:
            with h5py.File(self.filename, 'r', libver='latest', swmr=True) as f:
                self.distanceComboBox.clear()
                self.distanceComboBox.addItems(
                    sorted(f['Samples'][self.sampleNameComboBox.currentText()],
                           key=lambda x: float(x)))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Cannot open H5 file",
                                           f"Error while opening H5 file: {self.filename}: {exc}")
        else:
            self.distanceComboBox.setEnabled(True)
            self.distanceSelected()

    @Slot()
    def distanceSelected(self):
        if ((self.distanceComboBox.currentIndex() >= 0) and
                (self.sampleNameComboBox.currentIndex() >= 0)
                and (self.filename is not None)):
            self.datasetSelected.emit(
                self.filename, self.sampleNameComboBox.currentText(), self.distanceComboBox.currentText())

    def loadExposure(self) -> Exposure:
        if ((self.filename is not None)
                and (self.sampleNameComboBox.currentIndex() >= 0)
                and (self.distanceComboBox.currentIndex() >= 0)):
            return Instrument.instance().io.loadH5(
                self.filename, self.sampleNameComboBox.currentText(), self.distanceComboBox.currentText())
        raise ValueError('Cannot load exposure: no file, no sample or no distance selected')
