import gc
import logging

from PyQt5 import QtCore, QtWidgets

from .exposuremodel import HeaderModel
from .exposureview_ui import Ui_MainWindow
from ...core.mixins import ToolWindow
from ...core.plotcurve import PlotCurve
from ...core.plotimage import PlotImage
from ....core.services.filesequence import FileSequence

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ExposureView(QtWidgets.QMainWindow, Ui_MainWindow, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo)
        self.setupUi(self)
        self._curve_cache={}

    def setupUi(self, MainWindow):
        Ui_MainWindow.setupUi(self, MainWindow)
        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Horizontal)
        self.plotContainer.setLayout(QtWidgets.QVBoxLayout())
        self.plotContainer.layout().addWidget(splitter)
        layout=self.plotContainer.layout()
        assert isinstance(layout, QtWidgets.QVBoxLayout)
        layout.setContentsMargins(0,0,0,0)
        self.plotImage = PlotImage()
        splitter.addWidget(self.plotImage)
        splitter.setContentsMargins(0,0,0,0)
        self.plotCurve = PlotCurve()
        splitter.addWidget(self.plotCurve)
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        self.prefixComboBox.addItems(sorted(fs.get_prefixes()))
        self.prefixComboBox.setCurrentIndex(0)
        self.firstFSNSpinBox.valueChanged.connect(self.onFirstFSNChanged)
        self.lastFSNSpinBox.valueChanged.connect(self.onLastFSNChanged)
        self.updateSpinBoxLimits()
        self.prefixComboBox.currentTextChanged.connect(self.onPrefixChanged)
        self.headerModel=HeaderModel(self, self.credo, self.prefixComboBox.currentText(),
                                     self.firstFSNSpinBox.value(), self.lastFSNSpinBox.value())
        self.treeView.setModel(self.headerModel)
        self.reloadPushButton.clicked.connect(self.reloadHeaders)
        self.treeView.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.treeView.selectionModel().currentRowChanged.connect(self.onCurrentRowChanged)
        self.reloadHeaders()

    def onSelectionChanged(self):
        logger.debug('onSelectionChanged')
        fsns = []
        selected = self.treeView.selectionModel().selectedRows()
        for idx in selected:
            fsns.append(self.headerModel.data(self.headerModel.index(idx.row(), 0), QtCore.Qt.DisplayRole))
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        self.plotCurve.clear()
        logger.debug('Loading curves')
        for f in sorted(set(fsns)):
            try:
                rad, title = self._curve_cache[f]
                logger.debug('Curve for FSN {:d} found in cache.'.format(f))
            except KeyError:
                ex=fs.load_exposure(self.prefixComboBox.currentText(), f)
                rad = ex.radial_average()
                self._curve_cache[f] = (rad, ex.header.title)
                title = ex.header.title
                logger.debug('Curve for FSN {:d} not found in cache.'.format(f))
            self.plotCurve.addCurve(rad, label='{:d}: {}'.format(f, title), hold_mode=True)
        self.plotCurve.setXLabel('q (nm$^{-1}$)')
        self.plotCurve.setYLabel('Total counts')
        logger.debug('onSelectionChanged finished')

    def onCurrentRowChanged(self, current:QtCore.QModelIndex, previous:QtCore.QModelIndex):
        logger.debug('onCurrentRowChanged')
        fsn = self.headerModel.data(self.headerModel.index(current.row(),0), QtCore.Qt.DisplayRole)
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        ex = fs.load_exposure(self.prefixComboBox.currentText(), fsn)
        self.plotImage.setExposure(ex)
        logger.debug('onCurrentRowChanged finished')

    def onFirstFSNChanged(self):
        self.lastFSNSpinBox.setMinimum(self.firstFSNSpinBox.value())

    def onLastFSNChanged(self):
        self.firstFSNSpinBox.setMaximum(self.lastFSNSpinBox.value())

    def onPrefixChanged(self):
        self.updateSpinBoxLimits()
        self.reloadHeaders()

    def updateSpinBoxLimits(self):
        logger.debug('updateSpinBoxLimits')
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        prefix = self.prefixComboBox.currentText()
        maxfsn = fs.get_lastfsn(prefix)
        self.firstFSNSpinBox.setMinimum(0)
        self.firstFSNSpinBox.setMaximum(maxfsn)
        self.lastFSNSpinBox.setMinimum(0)
        self.lastFSNSpinBox.setMaximum(maxfsn)
        self.lastFSNSpinBox.setValue(maxfsn)
        self.firstFSNSpinBox.setValue(max(0, maxfsn-100))

    def reloadHeaders(self):
        logger.debug('reloadHeaders')
        self._curve_cache = {}
        self.headerModel.prefix= self.prefixComboBox.currentText()
        self.headerModel.fsnfirst = self.firstFSNSpinBox.value()
        self.headerModel.fsnlast = self.lastFSNSpinBox.value()
        self.headerModel.reloadHeaders()
        self.treeView.selectionModel().select(self.headerModel.index(0,0), QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
        self.treeView.selectionModel().setCurrentIndex(self.headerModel.index(0,0), QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
        gc.collect()
        logger.debug('reloadHeaders finished')
