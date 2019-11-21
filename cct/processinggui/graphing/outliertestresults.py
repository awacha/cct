import time
from typing import Union, Any

import dateutil.parser
import numpy as np
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from . import ImageView, CurveView
from .outliertestresults_ui import Ui_Form
from ..models.outliers import OutlierTestResults


class OutlierViewer(QtWidgets.QWidget, Ui_Form):
    figure: Figure = None
    canvas: FigureCanvasQTAgg = None
    figToolbar: NavigationToolbar2QT = None
    axes: Axes = None
    _highlight: Line2D = None
    _lastfsns: np.ndarray = None
    _lastscores: np.ndarray = None

    def __init__(self, parent: QtWidgets.QWidget = None, project: "Project" = None):
        super().__init__(parent)
        self.project = project
        if self.project is None:
            raise ValueError('Outlier viewer needs a project')
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(figsize=(6, 4), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figToolbar = NavigationToolbar2QT(self.canvas, self)
        self.figureVerticalLayout.addWidget(self.figToolbar)
        self.figureVerticalLayout.addWidget(self.canvas, 1)
        self.canvas.mpl_connect('resize_event', self.onCanvasResize)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding)
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.project.newResultsAvailable.connect(self.updateSampleList)
        self.sampleNameComboBox.currentIndexChanged.connect(self.onSampleChanged)
        self.distanceComboBox.currentIndexChanged.connect(self.onDistanceChanged)
        self.model = OutlierTestResults()
        self.outlierMethodComboBox.addItems(self.project.config.acceptableValues('outliermethod'))
        self.treeView.setModel(self.model)
        self.fromConfig()
        self.outlierMethodComboBox.currentIndexChanged.connect(self.replot)
        self.project.config.configItemChanged.connect(self.onConfigChanged)
        self.updateSampleList()
        self.plotCurvePushButton.clicked.connect(self.plotCurve)
        self.plotImagePushButton.clicked.connect(self.plotImage)
        self.treeView.selectionModel().selectionChanged.connect(self.onSelectionChanged)

    def onSelectionChanged(self):
        self.plotCurvePushButton.setEnabled(len(self.treeView.selectionModel().selectedRows(0))>0)
        self.plotImagePushButton.setEnabled(self.plotCurvePushButton.isEnabled())
        self.plotHighlights()

    def plotCurve(self):
        cv = CurveView(None, self.project)
        cv.setWindowTitle('Curves')
        for index in self.treeView.selectionModel().selectedRows():
            curve = self.project.h5reader.getCurve(self.sampleNameComboBox.currentText(), self.distanceComboBox.currentText(), self.model[index.row()].fsn)
            cv.addCurve(curve, label='#{}'.format(self.model[index.row()].fsn))
        cv.replot()
        self.project.subwindowOpenRequest.emit('outliertest_showcurve_{}'.format(time.monotonic()), cv)

    def plotImage(self):
        for index in self.treeView.selectionModel().selectedRows():
            fsn = self.model[index.row()].fsn
            try:
                ex = self.project.loadExposure(int(fsn))
            except FileNotFoundError:
                continue
            iv = ImageView(None, self.project.config)
            iv.setWindowTitle('#{}'.format(fsn))
            iv.setExposure(ex)
            self.project.subwindowOpenRequest.emit('outliertest_showimage_{}'.format(time.monotonic()), iv)

    def onConfigChanged(self, section: str, itemname: str, newvalue: Any):
        if itemname == 'outliermethod':
            self.outlierMethodComboBox.setCurrentIndex(self.outlierMethodComboBox.findText(newvalue))

    def fromConfig(self):
        self.outlierMethodComboBox.setCurrentIndex(
            self.outlierMethodComboBox.findText(self.project.config.outliermethod))

    def onSampleChanged(self):
        # sample changed, update the distance combo box
        currentdistance = float(self.distanceComboBox.currentText()) if self.distanceComboBox.currentIndex() >= 0 else 0
        self.distanceComboBox.blockSignals(True)
        try:
            self.distanceComboBox.clear()
            distances = sorted(self.project.h5reader.distanceKeys(self.sampleNameComboBox.currentText()))
            self.distanceComboBox.addItems(distances)
            targetdistance = sorted(distances, key=lambda dist: abs(float(dist) - currentdistance))[0]
            self.distanceComboBox.setCurrentIndex(self.distanceComboBox.findText(targetdistance))
        finally:
            self.distanceComboBox.blockSignals(False)
        self.onDistanceChanged()

    def onDistanceChanged(self):
        self.replot()

    def plotHighlights(self):
        if self._highlight is not None:
            self._highlight.remove()
            self._highlight = None
        fsns = [self.model[index.row()].fsn for index in self.treeView.selectionModel().selectedRows(0)]
        scores = [s for f, s in zip(self._lastfsns, self._lastscores) if int(f) in fsns]
        indices = [i for i, f in enumerate(self._lastfsns) if int(f) in fsns]
        self._highlight=self.axes.plot(indices, scores, 'o', markerfacecolor='none', markersize=10, markeredgecolor='b')[0]
        self.canvas.draw_idle()

    def replot(self):
        # get the data
        dates = self.project.h5reader.getCurveParameter(self.sampleNameComboBox.currentText(),
                                                        self.distanceComboBox.currentText(),
                                                        'date')
        if self.outlierMethodComboBox.currentText() == 'Z-score':
            scores = self.project.h5reader.getCurveParameter(self.sampleNameComboBox.currentText(),
                                                             self.distanceComboBox.currentText(),
                                                             'correlmat_zscore')
            isbads = self.project.h5reader.getCurveParameter(self.sampleNameComboBox.currentText(),
                                                             self.distanceComboBox.currentText(),
                                                             'correlmat_bad_zscore')
        elif self.outlierMethodComboBox.currentText() == 'Modified Z-score':
            scores = self.project.h5reader.getCurveParameter(self.sampleNameComboBox.currentText(),
                                                             self.distanceComboBox.currentText(),
                                                             'correlmat_zscore_mod')
            isbads = self.project.h5reader.getCurveParameter(self.sampleNameComboBox.currentText(),
                                                             self.distanceComboBox.currentText(),
                                                             'correlmat_bad_zscore_mod')
        elif self.outlierMethodComboBox.currentText() == 'Interquartile Range':
            discrp = self.project.h5reader.getCurveParameter(self.sampleNameComboBox.currentText(),
                                                             self.distanceComboBox.currentText(),
                                                             'correlmat_discrp')
            mean = np.nanmean(list(discrp.values()))
            std = np.nanstd(list(discrp.values()))
            scores = {fsn: (d - mean) / std for fsn, d in discrp.items()}
            isbads = self.project.h5reader.getCurveParameter(self.sampleNameComboBox.currentText(),
                                                             self.distanceComboBox.currentText(),
                                                             'correlmat_bad_iqr')
        else:
            raise ValueError('Invalid outlier method: {}'.format(self.outlierMethodComboBox.currentText()))
        fsns = sorted(list(scores.keys()))
        verdicts = ['GOOD' if not isbads[x] else
                    ('BAD' if np.isfinite(scores[x]) else 'ALREADY BAD') for x in fsns]
        scores = [scores[x] for x in fsns]
        dates = [dateutil.parser.parse(dates[x]) for x in fsns]
        # update the tree model
        self.model.setValues(fsns, dates, scores, verdicts)
        for c in range(self.model.columnCount()):
            self.treeView.resizeColumnToContents(c)
        bad = np.array([bool(isbads[x]) for x in fsns])
        scores = np.array(scores)
        # replot
        self.axes.clear()
        x = np.arange(len(fsns))
        self.axes.plot(x[~bad], scores[~bad], 'bo')
        self.axes.plot(x[bad], scores[bad], 'rx')
        self._lastfsns = np.array(fsns)
        self._lastscores = scores
        self.axes.axhline(np.nanmean(scores), linestyle='--', color='k', lw=1)
        if self.outlierMethodComboBox.currentText() == 'Interquartile Range':
            q1, q3 = np.percentile(scores[np.isfinite(scores)], [25, 75])
            iqr = q3 - q1
            self.axes.axhspan(q1 - iqr * self.project.config.std_multiplier,
                              q3 + iqr * self.project.config.std_multiplier,
                              fill=True, facecolor='lightgreen', edgecolor='none', alpha=0.5)
        else:
            self.axes.axhspan(-self.project.config.std_multiplier,
                              +self.project.config.std_multiplier,
                              fill=True, facecolor='lightgreen', edgecolor='none', alpha=0.5)
        self.axes.set_xlabel('FSN')
        self.axes.xaxis.set_ticks(x)
        self.axes.xaxis.set_ticklabels([str(f) for f in fsns], rotation=90)
        self.axes.set_ylabel('Outlier score')
        self._highlight = None
        self.plotHighlights()
        self.canvas.draw()
        self.setWindowTitle('Outliers of sample {} @ {}'.format(self.sampleNameComboBox.currentText(),
                                                                self.distanceComboBox.currentText()))

    def onCanvasResize(self, event):
        pass

    def setSampleAndDistance(self, samplename: str, distance: Union[str, float]):
        if isinstance(distance, float):
            distance = '{:.2f}'.format(distance)
        self.sampleNameComboBox.setCurrentIndex(self.sampleNameComboBox.findText(samplename))
        self.distanceComboBox.setCurrentIndex(self.distanceComboBox.findText(distance))

    def updateSampleList(self):
        currentsample = self.sampleNameComboBox.currentText()
        samples = self.project.h5reader.samples()
        self.sampleNameComboBox.blockSignals(True)
        try:
            self.sampleNameComboBox.clear()
            self.sampleNameComboBox.addItems(samples)
            self.sampleNameComboBox.setCurrentIndex(self.sampleNameComboBox.findText(currentsample))
            if self.sampleNameComboBox.currentIndex() < 0:
                self.sampleNameComboBox.setCurrentIndex(0)
        finally:
            self.sampleNameComboBox.blockSignals(False)
        self.onSampleChanged()
