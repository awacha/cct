from PyQt5 import QtWidgets, QtCore
from .persampletool_ui import Ui_Form
from ..toolbase import ToolBase
from ....core.processing.summarize import Summarizer
from ....qtgui.tools.anisotropy import AnisotropyEvaluator
from ...display import show_cmatrix, display_outlier_test_results_graph, display_outlier_test_results, summarize_curves, show_scattering_image
import h5py

import logging
import matplotlib.colors

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class PerSampleTool(ToolBase, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.resultsDistanceSelectorComboBox.setEnabled(False)
        self.resultsSampleSelectorComboBox.setEnabled(False)
        self.resultsSampleSelectorComboBox.currentIndexChanged.connect(self.onResultsSampleSelected)
        self.resultsDistanceSelectorComboBox.currentIndexChanged.connect(self.onResultsDistanceSelected)
        self.plotCorMatPushButton.setEnabled(False)
        self.plotCorMatTestResultsPushButton.setEnabled(False)
        self.plotCurvesPushButton.setEnabled(False)
        self.plotImagePushButton.setEnabled(False)
        self.plotCorMatTestResultsPushButton.clicked.connect(self.onPlotCorMatResults)
        self.plotCorMatPushButton.clicked.connect(self.onPlotCorMat)
        self.plotCurvesPushButton.clicked.connect(self.onPlotCurves)
        self.plotAnisotropyPushButton.clicked.connect(self.onPlotAnisotropy)
        self.plotImagePushButton.clicked.connect(self.onPlotImage)
        self.configWidgets = [
            (self.plot1dShowMeanCurveCheckBox, 'persample', 'showmeancurve'),
            (self.plot1dShowBadCurvesCheckBox, 'persample', 'showbadcurves'),
            (self.plot1dShowGoodCurvesCheckBox, 'persample', 'showgoodcurves'),
            (self.plot1dLogarithmicXCheckBox, 'persample', 'logx'),
            (self.plot1dLogarithmicYCheckBox, 'persample', 'logy'),
            (self.plot2dShowMaskCheckBox, 'persample', 'showmask'),
            (self.plot2dShowCenterCheckBox, 'persample', 'showcenter'),
        ]


    def onPlotAnisotropy(self):
        a=AnisotropyEvaluator(self, credo=None)
        a.h5Selector.h5FileNameLineEdit.setText(self.h5FileName)
        a.h5Selector.reloadFile()
        a.h5Selector.sampleNameComboBox.setCurrentIndex(a.h5Selector.sampleNameComboBox.findText(self.resultsSampleSelectorComboBox.currentText()))
        a.h5Selector.distanceComboBox.setCurrentIndex(a.h5Selector.distanceComboBox.findText(self.resultsDistanceSelectorComboBox.currentText()))
        a.show()

    @property
    def sample(self) -> str:
        return self.resultsSampleSelectorComboBox.currentText()

    @property
    def distance(self) -> str:
        return self.resultsDistanceSelectorComboBox.currentText()

    def onPlotCorMat(self):
        with self.getHDF5Group(self.sample, self.distance) as grp:
            show_cmatrix(self.figure, grp)
        self.figureDrawn.emit()

    def onPlotCorMatResults(self):
        with self.getHDF5Group(self.sample, self.distance) as grp:
            if 'curves' not in grp:
                QtWidgets.QMessageBox.information(
                    self,
                    'Cannot show outlier test results',
                    'Sample {} has no direct measured curves associated: possibly a subtracted sample.'.format(
                        self.resultsSampleSelectorComboBox.currentText()))
                return
            model = display_outlier_test_results(grp['curves'])
            display_outlier_test_results_graph(self.figure, grp['curves'], self.siblings['processing'].stdMultiplier,
                                               ['zscore','zscore_mod','iqr'][self.siblings['processing'].corrMatMethodIdx])
        self.treeView.setModel(model)
        self.tableShown.emit()

    def onPlotCurves(self):
        with self.getHDF5Group(self.sample, self.distance) as grp:
            if 'curves' not in grp:
                QtWidgets.QMessageBox.information(
                    self,
                    'Cannot plot curves',
                    'Sample {} has no direct measured curves associated: possibly a subtracted sample.'.format(
                        self.resultsSampleSelectorComboBox.currentText()))
                return
            summarize_curves(self.figure, grp['curves'], self.plot1dShowGoodCurvesCheckBox.isChecked(),
                             self.plot1dShowBadCurvesCheckBox.isChecked(),
                             self.plot1dShowMeanCurveCheckBox.isChecked(),
                             self.plot1dLogarithmicXCheckBox.isChecked(),
                             self.plot1dLogarithmicYCheckBox.isChecked())
        self.figureDrawn.emit()

    def onPlotImage(self):
        with self.getHDF5Group(self.sample, self.distance) as grp:
            show_scattering_image(self.figure, grp, self.plot2dShowMaskCheckBox.isChecked(),
                                  self.plot2dShowCenterCheckBox.isChecked(), )
        self.figureDrawn.emit()

    def onResultsSampleSelected(self):
        if not len(self.resultsSampleSelectorComboBox):
            return
        try:
            with h5py.File(self.h5FileName, 'r') as f:
                self.resultsDistanceSelectorComboBox.clear()
                self.resultsDistanceSelectorComboBox.addItems(
                    sorted(f['Samples'][self.resultsSampleSelectorComboBox.currentText()],
                           key=lambda x: float(x)))
                self.resultsDistanceSelectorComboBox.setCurrentIndex(0)
        except (FileNotFoundError, ValueError, OSError):
            return

    def onResultsDistanceSelected(self):
        self.plotImagePushButton.setEnabled(self.resultsDistanceSelectorComboBox.currentIndex() >= 0)
        self.plotCurvesPushButton.setEnabled(self.resultsDistanceSelectorComboBox.currentIndex() >= 0)
        self.plotCorMatPushButton.setEnabled(self.resultsDistanceSelectorComboBox.currentIndex() >= 0)
        self.plotCorMatTestResultsPushButton.setEnabled(self.resultsDistanceSelectorComboBox.currentIndex() >= 0)

    def setH5FileName(self, h5filename:str):
        super().setH5FileName(h5filename)
        self.resultsSampleSelectorComboBox.clear()
        self.resultsSampleSelectorComboBox.addItems(self.h5GetSamples())
        self.resultsSampleSelectorComboBox.setCurrentIndex(0)
        self.resultsSampleSelectorComboBox.setEnabled(True)
        self.resultsDistanceSelectorComboBox.setEnabled(True)
