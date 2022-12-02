from typing import Optional

import h5py
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot

from .blocksignalscontextmanager import SignalsBlocked
from .filebrowsers import getOpenFile
from .h5selector_ui import Ui_Form
from ...core2.dataclasses import Exposure
from ...core2.instrument.instrument import Instrument


class H5Selector(QtWidgets.QWidget, Ui_Form):
    filename: Optional[str] = None
    datasetSelected = Signal(str, str, str, name='datasetSelected')
    horizontal: bool = True

    def __init__(self, parent: QtWidgets.QWidget, horizontal: bool = True):
        super().__init__(parent)
        self.horizontal = horizontal
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        if not self.horizontal:
            self.horizontalLayout.removeWidget(self.browsePushButton)
            self.horizontalLayout.removeWidget(self.sampleNameComboBox)
            self.horizontalLayout.removeWidget(self.distanceComboBox)
            self.horizontalLayout.removeWidget(self.reloadToolButton)
            grid: QtWidgets.QGridLayout = QtWidgets.QGridLayout(self)
            self.horizontalLayout.addLayout(grid, 1)
            grid.addWidget(QtWidgets.QLabel(self, text='File:'), 0, 0, 1, 1)
            grid.addWidget(self.browsePushButton, 0, 1, 1, 1)
            grid.addWidget(QtWidgets.QLabel(self, text='Sample:'), 1, 0, 1, 1)
            grid.addWidget(self.sampleNameComboBox, 1, 1, 1, 1)
            grid.addWidget(QtWidgets.QLabel(self, text='Distance:'), 2, 0, 1, 1)
            grid.addWidget(self.distanceComboBox, 2, 1, 1, 1)
            grid.addWidget(self.reloadToolButton, 0, 2, 1, 1)
            self.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding, QtWidgets.QSizePolicy.Policy.MinimumExpanding)
        self.distanceComboBox.setEnabled(False)
        self.sampleNameComboBox.setEnabled(False)
        self.browsePushButton.clicked.connect(self.browseH5FileName)
        self.sampleNameComboBox.currentIndexChanged.connect(self.sampleNameSelected)
        self.distanceComboBox.currentIndexChanged.connect(self.distanceSelected)

    @Slot()
    def browseH5FileName(self):
        filename = getOpenFile(
            self, "Select a HDF5 file", "", "CREDO Processed Data (*.cpt4);;HDF5 files (*.h5 *.hdf5);;All files (*)", )
        if not filename:
            return
        try:
            with h5py.File(filename, 'r', libver='latest', swmr=True) as f:
                samplenames = sorted(f['Samples'])
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Cannot open H5 file",
                                           f"Error while opening H5 file {filename}: {exc}")
            return
        currentsample = self.sampleNameComboBox.currentText() if self.sampleNameComboBox.currentIndex() >= 0 else None
        with SignalsBlocked(self.sampleNameComboBox):
            self.sampleNameComboBox.clear()
            if samplenames:
                self.sampleNameComboBox.addItems(samplenames)
                if currentsample is None:
                    self.sampleNameComboBox.setCurrentIndex(0)
                indexofoldcurrentsample = self.sampleNameComboBox.findText(currentsample)
                self.sampleNameComboBox.setCurrentIndex(indexofoldcurrentsample if indexofoldcurrentsample >= 0 else 0)

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
