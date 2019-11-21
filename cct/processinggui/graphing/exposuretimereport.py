from typing import Tuple, List, Union

import numpy as np
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.text import Text

from .exposuretimereport_ui import Ui_Form


class ExposureTimeReport(QtWidgets.QWidget, Ui_Form):
    figure: Figure = None
    canvas: FigureCanvasQTAgg = None
    figToolbar: NavigationToolbar2QT = None
    axes: Axes = None
    _samplesdistances = List[Tuple[str, Union[str, float]]]

    def __init__(self, parent: QtWidgets.QWidget = None, project: "Project" = None):
        super().__init__(parent)
        self.project = project
        if project is None:
            raise ValueError('Exposure time report needs a project')
        self._samplesdistances = []
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(figsize=(6, 4), constrained_layout=True)
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figToolbar = NavigationToolbar2QT(self.canvas, self)
        self.figureVerticalLayout.addWidget(self.figToolbar)
        self.figureVerticalLayout.addWidget(self.canvas, 1)
        self.canvas.mpl_connect('resize_event', self.onCanvasResize)
        self.canvas.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding)
        self.project.newResultsAvailable.connect(self.replot)
        self.reportTypeComboBox.currentIndexChanged.connect(self.replot)
        self.setWindowTitle('Exposure time report')

    def onCanvasResize(self, event):
        pass

    def replot(self):
        self.axes.clear()
        samplenames = {}
        distances = {}
        exptimes = {}
        badflags = {}

        for sample, distance in self._samplesdistances:
            samplenames.update(self.project.h5reader.getCurveParameter(sample, distance, 'title'))
            distances.update(self.project.h5reader.getCurveParameter(sample, distance, 'distance'))
            exptimes.update(self.project.h5reader.getCurveParameter(sample, distance, 'exposuretime'))
            badflags.update(self.project.h5reader.getCurveParameter(sample, distance, 'correlmat_bad'))
        fsns = sorted(list(samplenames.keys()))
        samplenames = [samplenames[f] for f in fsns]
        distances = [distances[f] for f in fsns]
        exptimes = [exptimes[f] for f in fsns]
        badflags = [bool(badflags[f]) for f in fsns]
        if self.reportTypeComboBox.currentText() == 'Time per sample (incl. outliers)':
            pievalues = {sn: sum([et for et, sn_ in zip(exptimes, samplenames) if sn_ == sn]) for sn in
                         set(samplenames)}
        elif self.reportTypeComboBox.currentText() == 'Time per sample (excl. outliers)':
            pievalues = {sn: sum([et for et, sn_, bf in zip(exptimes, samplenames, badflags) if sn_ == sn and not bf])
                         for sn in set(samplenames)}
        elif self.reportTypeComboBox.currentText() == 'Time per sample, distance (excl. outliers)':
            # although we could, for the sake of clarity we don't do this as a one-liner.
            pievalues = {}
            for samplename in set(samplenames):
                for distance in set([d for sn, d in zip(samplenames, distances) if sn == samplename]):
                    pievalues['{} @ {:.2f}'.format(samplename, distance)] = sum(
                        [et for et, sn, d, bf in zip(exptimes, samplenames, distances, badflags) if
                         sn == samplename and d == distance and not bf]
                    )
        elif self.reportTypeComboBox.currentText() == 'Time per sample, distance (incl. outliers)':
            # although we could, for the sake of clarity we don't do this as a one-liner.
            pievalues = {}
            for samplename in set(samplenames):
                for distance in set([d for sn, d in zip(samplenames, distances) if sn == samplename]):
                    pievalues['{} @ {:.2f}'.format(samplename, distance)] = sum(
                        [et for et, sn, d in zip(exptimes, samplenames, distances) if
                         sn == samplename and d == distance]
                    )
        elif self.reportTypeComboBox.currentText() == 'Time for outliers vs. time for valid exposures':
            pievalues = {'Valid': sum([et for et, bf in zip(exptimes, badflags) if not bf]),
                         'Outlier': sum([et for et, bf in zip(exptimes, badflags) if bf])}
        else:
            raise ValueError('Invalid report type: {}'.format(self.reportTypeComboBox.currentText()))
        keys = sorted(pievalues)
        values = np.array([pievalues[k] for k in keys])
        hours = values // 3600
        minutes = (values - 3600 * hours) // 60
        seconds = (values - 3600 * hours - 60 * minutes)
        labels = ['{}\n({:.0f}:{:.0f}:{:.0f})'.format(k, h, m, s) for k, h, m, s in zip(keys, hours, minutes, seconds)]
        patches, texts= self.axes.pie(values, labels=labels, rotatelabels=True, textprops={'fontsize':'small'})
        for t in texts:
            assert isinstance(t, Text)
        #self.axes.legend(loc='best')
        self.canvas.draw()

    def addSampleAndDistance(self, samplename: str, distance: Union[str, float], replot: bool = True):
        self._samplesdistances.append((samplename, distance))
        if replot:
            self.replot()
