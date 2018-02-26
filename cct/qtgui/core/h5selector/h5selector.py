import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from PyQt5 import QtWidgets, QtCore
from ..mixins import ToolWindow
from .h5selector_ui import Ui_Form
from sastool.io.credo_cpth5 import Exposure
import h5py


class H5Selector(QtWidgets.QWidget, Ui_Form, ToolWindow):
    H5Selected = QtCore.pyqtSignal(str, str, float, Exposure)

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo', None)
        self.horizontal = kwargs.pop('horizontal', False)
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        if self.horizontal:
            self.hlayout = QtWidgets.QHBoxLayout()
            self.hlayout.setContentsMargins(0, 0, 0, 0)
            self.hlayout.addWidget(self.label)
            self.hlayout.addWidget(self.h5FileNameLineEdit)
            self.hlayout.addWidget(self.browseFilePushButton)
            self.hlayout.addWidget(self.label_2)
            self.hlayout.addWidget(self.sampleNameComboBox)
            self.hlayout.addWidget(self.label_3)
            self.hlayout.addWidget(self.distanceComboBox)
            self.hlayout.addWidget(self.reloadFilePushButton)
            self.reloadFilePushButton.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Maximum)
            self.reloadFilePushButton.setText('Reload file')
            self.hlayout.addSpacerItem(
                QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Minimum))
            del self.gridLayout
            QtWidgets.QWidget().setLayout(self.layout())  # an ugly trick to get rid of the original layout
            self.setLayout(self.hlayout)
        self.browseFilePushButton.clicked.connect(self.onBrowseFile)
        self.reloadFilePushButton.clicked.connect(self.reloadFile)
        self.sampleNameComboBox.currentIndexChanged.connect(self.onSampleNameChanged)
        self.distanceComboBox.currentIndexChanged.connect(self.onDistanceChanged)

    def onBrowseFile(self):
        filename, filter = QtWidgets.QFileDialog.getOpenFileName(self, 'Open a HDF5 file made by CPT...', self.windowFilePath(), 'HDF5 files (*.h5 *.hdf5);;All files (*)', 'HDF5 files (*.h5 *.hdf5)')
        if not filename:
            return
        self.h5FileNameLineEdit.setText(filename)
        self.reloadFile()

    def reloadFile(self):
        with h5py.File(self.h5FileNameLineEdit.text(), 'r') as f:
            samples = sorted(list(f['Samples'].keys()))
        self.sampleNameComboBox.blockSignals(True)
        self.sampleNameComboBox.setEnabled(True)
        prevsamplename = self.sampleNameComboBox.currentText()
        try:
            self.sampleNameComboBox.clear()
            self.sampleNameComboBox.addItems(samples)
        finally:
            self.sampleNameComboBox.blockSignals(False)
        idx = max(0,self.sampleNameComboBox.findText(prevsamplename))
        self.sampleNameComboBox.setCurrentIndex(idx)
        self.onSampleNameChanged()

    def onSampleNameChanged(self):
        self.distanceComboBox.setEnabled(True)
        with h5py.File(self.h5FileNameLineEdit.text(), 'r') as f:
            dists = sorted(list(f['Samples'][self.sampleNameComboBox.currentText()].keys()),
                           key=lambda x:float(x))
        self.distanceComboBox.blockSignals(True)
        prevdistance = self.distanceComboBox.currentText()
        try:
            self.distanceComboBox.clear()
            self.distanceComboBox.addItems(dists)
        finally:
            self.distanceComboBox.blockSignals(False)
        idx = max(0, self.distanceComboBox.findText(prevdistance))
        self.distanceComboBox.setCurrentIndex(idx)
        self.onDistanceChanged()

    def onDistanceChanged(self):
        self.loadExposure()
        self.H5Selected.emit(self.h5FileNameLineEdit.text(), self.sampleNameComboBox.currentText(), float(self.distanceComboBox.currentText()), self._exposure)

    def cleanup(self):
        super().cleanup()

    def loadExposure(self):
        self._exposure = Exposure.new_from_file(self.h5FileNameLineEdit.text(), self.sampleNameComboBox.currentText(), float(self.distanceComboBox.currentText()))
        return self._exposure

    def exposure(self):
        return self._exposure
