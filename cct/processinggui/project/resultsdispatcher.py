import logging
import re
from time import monotonic
from typing import Sequence, Tuple

from PyQt5 import QtCore, QtWidgets, QtGui

from .resultsdispatcher_ui import Ui_Form
from ..config import Config
from ..graphing import ImageView, CurveView, CorrMatView, VacuumFluxViewer, OutlierViewer, ExposureTimeReport
from ..models.results import ResultsModel
from ...qtgui.tools.anisotropy import AnisotropyEvaluator

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class RegExpValidator(QtGui.QValidator):
    def validate(self, line: str, pos: int) -> Tuple[QtGui.QValidator.State, str, int]:
        try:
            re.compile(line)
            return self.Acceptable, line, pos
        except re.error:
            return self.Intermediate, line, pos
        assert False


class ResultsDispatcher(QtWidgets.QWidget, Ui_Form):
    subwindowOpenRequest = QtCore.pyqtSignal(str, QtWidgets.QWidget, name='subwindowOpenRequest')

    def __init__(self, parent: QtWidgets.QWidget, config:Config, project:"Project"):
        super().__init__(parent)
        self.config = config
        self.config.configItemChanged.connect(self.onConfigItemChanged)
        self.project = project
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.model = ResultsModel(self.config.hdf5)
        self.treeView.setModel(self.model)
        self.model.modelReset.connect(self.resizeTreeViewColumns)
        self.model.dataChanged.connect(self.resizeTreeViewColumns)
        self.treeView.header().sortIndicatorChanged.connect(self.onTreeHeaderSortIndicatorChanged)
        self.perSampleImagePushButton.clicked.connect(self.onPerSampleImage)
        self.perSampleCurvesPushButton.clicked.connect(self.onPerSampleCurves)
        self.perSampleCorrelationMatrixPushButton.clicked.connect(self.onPersampleCorrMat)
        self.perSampleOutlierTestPushButton.clicked.connect(self.onPerSampleOutlierTest)
        self.perSampleAnisotropyPushButton.clicked.connect(self.onPerSampleAnisotropy)
        self.overallCurvesPushButton.clicked.connect(self.onOverallCurves)
        self.overallExposureTimePushButton.clicked.connect(self.onOverallExposureTime)
        self.overallTransmissionPushButton.clicked.connect(self.onOverallTransmission)
        self.overallVacuumFluxPushButton.clicked.connect(self.onOverallVacuumFlux)
        self.selectAllSamplesToolButton.clicked.connect(self.selectAllSamples)
        self.selectNoSamplesToolButton.clicked.connect(self.selectNoSamples)
        self.selectRegexToolButton.clicked.connect(self.selectRegex)
        self.deselectRegexToolButton.clicked.connect(self.deselectRegex)
        self.regexpValidator = RegExpValidator()
        self.sampleNameRegexLineEdit.setValidator(self.regexpValidator)
        self.sampleNameRegexLineEdit.textChanged.connect(self.onRegexInvalid)
        self.resizeTreeViewColumns()

    def onRegexInvalid(self):
        self.selectRegexToolButton.setEnabled(self.sampleNameRegexLineEdit.hasAcceptableInput())
        self.deselectRegexToolButton.setEnabled(self.sampleNameRegexLineEdit.hasAcceptableInput())

    def selectAllSamples(self):
        self.treeView.selectAll()

    def selectNoSamples(self):
        self.treeView.clearSelection()

    def selectRegex(self):
        try:
            regexp = re.compile(self.sampleNameRegexLineEdit.text())
        except re.error:
            assert False
        for i in range(self.model.rowCount()):
            if regexp.match(self.model[i].samplename):
                self.treeView.selectionModel().select(self.model.index(i, 0), QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)

    def deselectRegex(self):
        try:
            regexp = re.compile(self.sampleNameRegexLineEdit.text())
        except re.error:
            assert False
        for i in range(self.model.rowCount()):
            if regexp.match(self.model[i].samplename):
                self.treeView.selectionModel().select(self.model.index(i, 0), QtCore.QItemSelectionModel.Deselect | QtCore.QItemSelectionModel.Rows)

    def onOverallCurves(self):
        cv = CurveView()
        for sample, distance in self.selectedResults():
            logger.debug('Adding curve to overall curve comparison: {}, {}'.format(sample, distance))
            curve = self.project.h5reader.averagedCurve(sample, distance)
            cv.addCurve(curve, (sample, distance), label='{} @{:.2f} mm'.format(sample, distance))
        cv.replot()
        cv.setWindowTitle('Compare curves')
        self.subwindowOpenRequest.emit('curve_compare_{}'.format(monotonic()), cv)

    def onOverallExposureTime(self):
        etr = ExposureTimeReport(None, self.project)
        for samplename, distance in self.selectedResults():
            etr.addSampleAndDistance(samplename, distance, False)
        etr.replot()
        self.subwindowOpenRequest.emit('exptimereport_{}'.format(monotonic()), etr)

    def onOverallTransmission(self):
        pass

    def onOverallVacuumFlux(self):
        vf = VacuumFluxViewer(None, self.project)
        for samplename, distance in self.selectedResults():
            vf.addSampleAndDist(samplename, distance, replot=False)
        vf.replot()
        self.subwindowOpenRequest.emit('vacuumandflux_{}'.format(monotonic()), vf)

    def onTreeHeaderSortIndicatorChanged(self, logicalsection:int, sortorder:QtCore.Qt.SortOrder):
        logger.debug('Sort order changed: section {}, order {}'.format(logicalsection, sortorder))
        self.treeView.sortByColumn(logicalsection, sortorder)

    def resizeTreeViewColumns(self):
        for c in range(self.model.columnCount()):
            self.treeView.resizeColumnToContents(c)

    def reloadResults(self):
        self.model.reload()
        self.model.sort(self.treeView.header().sortIndicatorSection(), self.treeView.header().sortIndicatorOrder())

    def onConfigItemChanged(self, section, itemname, newvalue):
        if itemname == 'hdf5':
            self.model.setH5FileName(newvalue)

    def selectedResults(self) -> Sequence[Tuple[str, float]]:
        for idx in self.treeView.selectionModel().selectedRows(0):
            yield (self.model[idx.row()].samplename, float(self.model[idx.row()].distance))
        return

    def onPerSampleImage(self):
        for samplename, distance in self.selectedResults():
            iv = ImageView(None, config=self.project.config)
            iv.setExposure(self.project.h5reader.averagedImage(samplename, distance))
            iv.setWindowTitle('{} @ {:.2f}'.format(samplename, distance))
            self.subwindowOpenRequest.emit('persampleImage_{}'.format(monotonic()), iv)

    def onPerSampleCurves(self):
        for samplename, distance in self.selectedResults():
            cv = CurveView(None, self.project)
            avg = self.project.h5reader.averagedCurve(samplename, distance)
            badfsns = self.project.h5reader.badFSNs(samplename, distance)
            for fsn, curve in self.project.h5reader.allCurves(samplename, distance).items():
                cv.addCurve(curve, color='red' if int(fsn) in badfsns else 'green', label='#{}'.format(int(fsn)))
            cv.addCurve(avg, color='black', lw=1, label='Mean')
            cv.replot()
            cv.setWindowTitle('All exposures of {} @ {}'.format(samplename, distance))
            self.subwindowOpenRequest.emit('persampleCurve_{}_{}_{}'.format(samplename, distance, monotonic()), cv)

    def onPersampleCorrMat(self):
        for samplename, distance in self.selectedResults():
            cmatview = CorrMatView(None, self.project)
            cmatview.setCorrMat(self.project.h5reader.getCorrMat(samplename, distance),
                                sorted(list(self.project.h5reader.getCurveParameter(samplename, distance, 'fsn').keys())),
                                samplename, distance)
            self.subwindowOpenRequest.emit('cmat_{}_{}_{}'.format(samplename, distance, monotonic()), cmatview)

    def onPerSampleOutlierTest(self):
        for samplename, distance in self.selectedResults():
            ov = OutlierViewer(None, self.project)
            ov.setSampleAndDistance(samplename, distance)
            self.subwindowOpenRequest.emit('outlierviewer_{}_{}_{}'.format(samplename, distance, monotonic()), ov)

    def onPerSampleAnisotropy(self):
        for samplename, distance in self.selectedResults():
            ae = AnisotropyEvaluator()
            ae.h5Selector.close()
            ae.h5Selector.destroy()
            ae.setExposure(self.project.h5reader.averagedImage(samplename, distance))
            self.subwindowOpenRequest.emit('persampleAnisotropy_{}_{}_{}'.format(samplename, distance, monotonic()), ae)