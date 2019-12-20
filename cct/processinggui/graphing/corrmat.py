import logging
from typing import Union, Tuple

import matplotlib.cm
import numpy as np
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure

from .corrmat_ui import Ui_Form

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class CorrMatView(QtWidgets.QWidget, Ui_Form):
    cmat: np.ndarray = None
    fsns: np.ndarray = None
    axes: Axes = None
    figure: Figure = None
    canvas: FigureCanvasQTAgg = None
    toolbar: NavigationToolbar2QT = None
    _figsize: Tuple[float, float] = None

    def __init__(self, parent: QtWidgets.QWidget = None, project: "Project" = None,
                 figsize: Tuple[float, float] = (4, 4)):
        super().__init__(parent)
        self._figsize = figsize
        self.project = project
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(figsize=self._figsize, constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.figureVerticalLayout.addWidget(self.toolbar)
        self.figureVerticalLayout.addWidget(self.canvas)
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.paletteComboBox.addItems(sorted(matplotlib.cm.cmap_d))
        self.paletteComboBox.setCurrentIndex(self.paletteComboBox.findText(self.project.config.cmatpalette))
        if self.paletteComboBox.currentIndex() < 0:
            self.paletteComboBox.setCurrentIndex(0)
        self.project.newResultsAvailable.connect(self.onUpdateResults)
        self.paletteComboBox.currentIndexChanged.connect(self.onPaletteComboBoxChanged)
        self.sampleNameComboBox.currentIndexChanged.connect(self.onSampleNameComboBoxChanged)
        self.distanceComboBox.currentIndexChanged.connect(self.onDistanceComboBoxChanged)

    def setSampleAndDistance(self, samplename: str, distance: Union[str, float]):
        logger.debug('Setting sample name to {}, distance to {}'.format(samplename, distance))
        if self.project is not None:
            self.onUpdateResults()
        logger.debug(
            'After onUpdateResults, sample name is at {}, distance at {}'.format(self.sampleNameComboBox.currentText(),
                                                                                 self.distanceComboBox.currentText()))
        self.sampleNameComboBox.blockSignals(True)
        self.sampleNameComboBox.setCurrentIndex(self.sampleNameComboBox.findText(samplename))
        self.sampleNameComboBox.blockSignals(False)
        assert self.sampleNameComboBox.currentIndex() >= 0
        targetdist = distance if isinstance(distance, str) else '{:.2f}'.format(distance)
        self.distanceComboBox.blockSignals(True)
        self.distanceComboBox.setCurrentIndex(self.distanceComboBox.findText(targetdist))
        self.distanceComboBox.blockSignals(False)
        assert self.distanceComboBox.currentIndex() >= 0
        self.onDistanceComboBoxChanged()  # ensure that the correlation matrix is reloaded
        logger.debug('Sample name changed to {}, distance to {}'.format(self.sampleNameComboBox.currentText(),
                                                                        self.distanceComboBox.currentText()))
        logger.debug('Running replot')
        self.replot()

    def onUpdateResults(self):
        logger.debug('onUpdateResults')
        if self.project is None:
            return
        currentSample = self.sampleNameComboBox.currentText() if self.sampleNameComboBox.currentIndex() >= 0 else None
        self.sampleNameComboBox.blockSignals(True)
        try:
            self.sampleNameComboBox.clear()
            self.sampleNameComboBox.addItems(sorted(self.project.h5reader.samples()))
            target = self.sampleNameComboBox.findText(currentSample) if currentSample is not None else -1
            if target < 0:
                target = 0
        finally:
            self.sampleNameComboBox.blockSignals(False)
        logger.debug('Setting sample index to {}'.format(target))
        self.sampleNameComboBox.setCurrentIndex(target)
        self.onSampleNameComboBoxChanged()

    def replot(self):
        logger.debug('replot')
        if self.cmat is None:
            self.figure.clear()
            self.canvas.draw_idle()
            return
        self.figure.clear()
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.axes.clear()
        self.axes.set_adjustable('box')
        self.axes.set_aspect(1.0)
        img = self.axes.imshow(self.cmat, interpolation='nearest',
                               cmap=self.paletteComboBox.currentText(),
                               extent=[-0.5, self.cmat.shape[1]-0.5, self.cmat.shape[0]-0.5, -0.5], origin='upper')
        logger.debug('CMAT shape: {}'.format(self.cmat.shape))
        self.axes.xaxis.set_ticks(np.arange(self.cmat.shape[1]))
        self.axes.yaxis.set_ticks(np.arange(self.cmat.shape[0]))
        self.axes.xaxis.set_ticklabels([str(f) for f in self.fsns], rotation=90)
        self.axes.yaxis.set_ticklabels([str(f) for f in self.fsns])
        self.figure.colorbar(img, ax=self.axes)
        self.canvas.draw_idle()
        if self.sampleNameComboBox.isEnabled() and self.distanceComboBox.isEnabled():
            self.setWindowTitle('Correlation matrix: {} @{}'.format(self.sampleNameComboBox.currentText(),
                                                                    self.distanceComboBox.currentText()))

    def onPaletteComboBoxChanged(self):
        self.replot()

    def onSampleNameComboBoxChanged(self):
        logger.debug('Sample name changed to {}'.format(self.sampleNameComboBox.currentText()))
        if self.distanceComboBox.currentIndex() < 0:
            currentdist = None
        else:
            currentdist = float(self.distanceComboBox.currentText())
        distances = self.project.h5reader.distanceKeys(self.sampleNameComboBox.currentText())
        self.distanceComboBox.blockSignals(True)
        try:
            self.distanceComboBox.clear()
            self.distanceComboBox.addItems(sorted(distances, key=lambda x: float(x)))
            targetdist = sorted(distances, key=lambda d: abs(float(d) - currentdist))[0] \
                if currentdist is not None else distances[0]
        finally:
            self.distanceComboBox.blockSignals(False)
        self.distanceComboBox.setCurrentIndex(self.distanceComboBox.findText(targetdist))
        self.onDistanceComboBoxChanged()

    def onDistanceComboBoxChanged(self):
        logger.debug('Distance changed to {}'.format(self.distanceComboBox.currentText()))
        try:
            self.cmat = self.project.h5reader.getCorrMat(self.sampleNameComboBox.currentText(),
                                                         self.distanceComboBox.currentText())
            self.fsns = np.array(sorted(list(
                self.project.h5reader.getCurveParameter(self.sampleNameComboBox.currentText(),
                                                        self.distanceComboBox.currentText(), 'fsn').keys())))
            logger.debug('Got cmat and fsns from sample {}, distance {}'.format(self.sampleNameComboBox.currentText(),
                                                                                self.distanceComboBox.currentText()))
            logger.debug('cmat shape: {}. FSNS length: {}'.format(self.cmat.shape, len(self.fsns)))
        except OSError:
            return
        self.replot()

    def savefig(self, filename: str, **kwargs):
        self.canvas.draw()
        self.figure.savefig(
            filename,
            # format=None  # infer the format from the file name
            transparent=True,  # all patches will be transparent, instead of opaque white
            optimize=True,  # optimize JPEG file, ignore for other file types
            progressive=True,  # progressive JPEG, ignore for other file types
            quality=95,  # JPEG quality, ignore for other file types
            **kwargs
        )
