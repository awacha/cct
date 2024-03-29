import logging
import fractions
from typing import Dict, Any, Tuple, List, Optional

import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSlot as Slot

from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure

from .plotcurve_ui import Ui_Form
from ...core2.dataclasses import Curve

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class PlotCurve(QtWidgets.QWidget, Ui_Form):
    curves: List[Tuple[Curve, Dict[str, Any]]] = None
    figure: Figure
    axes: Axes
    axes_stddev: Optional[Axes]
    show_stddev: bool = False
    stddev_graph_height_ratio: fractions.Fraction = fractions.Fraction(3,1)
    canvas: FigureCanvasQTAgg
    navigationToolbar: NavigationToolbar2QT
    MARKERS: str = 'ovsp*D^h<H>x+d1234'
    _figsize: Tuple[float, float] = None

    def __init__(self, parent: QtWidgets.QWidget = None, figsize: Tuple[float, float] = (6, 6), show_stddev: bool = False, stddev_graph_height_ratio: Optional[fractions.Fraction] = None):
        super().__init__(parent)
        self._figsize = figsize
        self.curves = []
        if stddev_graph_height_ratio is not None:
            self.stddev_graph_height_ratio = stddev_graph_height_ratio
        self.show_stddev = show_stddev
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(figsize=self._figsize, constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.navigationToolbar = NavigationToolbar2QT(self.canvas, self)
        gridspec = self.figure.add_gridspec(
            self.stddev_graph_height_ratio.numerator + self.stddev_graph_height_ratio.denominator, 1)
        if not self.show_stddev:
            self.axes = self.figure.add_subplot(gridspec[:, :])
            self.axes_stddev = None
        else:
            self.axes = self.figure.add_subplot(gridspec[:self.stddev_graph_height_ratio.numerator, :])
            self.axes_stddev = self.figure.add_subplot(
                gridspec[self.stddev_graph_height_ratio.numerator:, :],
                sharex=self.axes)
        self.figureVerticalLayout.addWidget(self.navigationToolbar)
        self.figureVerticalLayout.addWidget(self.canvas)
        self.pixelOrQToolButton.toggled.connect(self.pixelOrQChanged)
        self.plotTypeComboBox.currentIndexChanged.connect(self.replot)
        self.showErrorBarsToolButton.toggled.connect(self.replot)
        self.showGridToolButton.toggled.connect(self.showGrid)
        self.showLegendToolButton.toggled.connect(self.showLegend)
        self.showLinesToolButton.toggled.connect(self.replot)
        self.symbolsTypeComboBox.currentIndexChanged.connect(self.replot)

    @Slot(bool)
    def pixelOrQChanged(self, state: bool):
        self.pixelOrQToolButton.setText('q' if state else 'Pixel')
        self.replot()

    def addCurve(self, curve: Curve, **kwargs):
        assert isinstance(curve, Curve)
        self.curves.append((curve, kwargs))
        logger.debug('Added a curve.')

    def on_showErrorBarsToolButton_toggled(self):
        self.replot()

    @Slot(bool)
    def showGrid(self, grid: bool):
        self.axes.grid(self.showGridToolButton.isChecked(), which='both')
        if self.axes_stddev is not None:
            self.axes_stddev.grid(self.showGridToolButton.isChecked(), which='both')
        self.canvas.draw()

    @Slot(bool)
    def showLegend(self, show: bool):
        self.axes.get_legend().set_visible(show)
        self.canvas.draw()

    @Slot()
    def replot(self):
        logger.debug('Replotting curves')
        if self.axes_stddev is not None:
            self.axes_stddev.clear()
            if (len({len(c.q) for c, kw in self.curves if c is not None}) == 1) and \
                    (np.nanmax(np.nanstd(np.vstack([c.q for c, kw in self.curves if c is not None]), axis=0)) < 0.0001):
                # all curves have the same q-range
                q = self.curves[0][0].q if self.pixelOrQToolButton.isChecked() else self.curves[0][0].pixel
                intensity_std = np.nanstd(np.vstack([c.intensity for c, kw in self.curves if c is not None]), axis=0)
                intensity_mean = np.nanmean(np.vstack([c.intensity for c, kw in self.curves if c is not None]), axis=0)
                self.axes_stddev.plot(
                    q, intensity_std/intensity_mean, ('-' if self.showLinesToolButton.isChecked() else '') +
                                      ('o' if (self.symbolsTypeComboBox.currentText() == 'No symbols') else ''),
                    mfc = ('none' if self.symbolsTypeComboBox.currentText() == 'Empty symbols' else 'k'),
                    mec = ('none' if self.symbolsTypeComboBox.currentText() == 'Empty symbols' else 'k'),
                    color = 'k',
                )
            else:
                self.axes_stddev.clear()
                self.axes_stddev.text(
                    0.5, 0.5, 'Not all curves are defined on the same $q$-range', ha='center', va='center',
                    transform=self.axes_stddev.transAxes)

        self.axes.clear()
        for i, (curve, kwargs) in enumerate(self.curves):
            if curve is None:
                # curve is temporarily absent.
                continue
            kwargs = kwargs.copy()  # do not change the original
            x = curve.q if self.pixelOrQToolButton.isChecked() else curve.pixel
            y = curve.intensity
            dx = curve.quncertainty if self.pixelOrQToolButton.isChecked() else np.zeros_like(x)
            dy = curve.uncertainty
            if self.plotTypeComboBox.currentText() == 'Kratky':
                dy = ((x ** 2 * dy) ** 2 + (2 * y * x * dx) ** 2) ** 0.5
                y = y * x ** 2
            elif self.plotTypeComboBox.currentText() == 'Porod':
                dy = ((x ** 4 * dy) ** 2 + (
                        4 * y * x ** 3 * dx) ** 2) ** 0.5
                y = y * x ** 4
            else:
                # do nothing
                pass
            if 'ls' in kwargs:
                # normalize: ls and linestyle are synonyms
                kwargs['linestyle'] = kwargs['ls']
                del kwargs['ls']
            if self.showLinesToolButton.isChecked() and ('linestyle' not in kwargs):
                # force drawing a line
                kwargs.setdefault('linestyle', '-')
                if not kwargs['linestyle']:
                    # if it is an empty string (as given by the user)
                    kwargs['linestyle'] = '-'
            elif 'linestyle' not in kwargs:
                # hide the line
                kwargs['linestyle'] = ''
            if (self.symbolsTypeComboBox.currentText() == 'No symbols') and ('marker' not in kwargs):
                # force hiding symbols
                kwargs['marker'] = ''
            elif 'marker' not in kwargs:
                # force drawing a symbol
                kwargs.setdefault('marker', self.MARKERS[i % len(self.MARKERS)])
                if not kwargs['marker']:
                    kwargs['marker'] = self.MARKERS[i % len(self.MARKERS)]
                if self.symbolsTypeComboBox.currentText() == 'Empty symbols':
                    kwargs['markerfacecolor'] = 'none'
                    try:
                        del kwargs['mfc']
                    except KeyError:
                        pass
                elif self.symbolsTypeComboBox.currentText() == 'Filled symbols':
                    kwargs['markerfacecolor'] = None
                    try:
                        del kwargs['mfc']
                    except KeyError:
                        pass
                else:
                    raise ValueError(self.symbolsTypeComboBox.currentText())
            logger.debug('Plotting curve #{} with kwargs {}'.format(i, kwargs))
            if self.showErrorBarsToolButton.isChecked():
                self.axes.errorbar(x, y, dy, dx, **kwargs)
            else:
                self.axes.plot(x, y, **kwargs)

        # adjust the axis scales
        if self.plotTypeComboBox.currentText() == 'log-log':
            self.axes.set_xscale('log')
            self.axes.set_yscale('log')
        elif self.plotTypeComboBox.currentText() == 'lin-log':
            self.axes.set_xscale('log')
            self.axes.set_yscale('linear')
        elif self.plotTypeComboBox.currentText() == 'log-lin':
            self.axes.set_xscale('linear')
            self.axes.set_yscale('log')
        elif self.plotTypeComboBox.currentText() == 'lin-lin':
            self.axes.set_xscale('linear')
            self.axes.set_yscale('linear')
        elif self.plotTypeComboBox.currentText() == 'Guinier':  # Guinier plot
            self.axes.set_xscale('guinier')
            self.axes.set_yscale('log')
        elif self.plotTypeComboBox.currentText() == 'Kratky':  # Kratky plot
            self.axes.set_xscale('linear')
            self.axes.set_yscale('linear')
        elif self.plotTypeComboBox.currentText() == 'Porod':  # Porod plot
            self.axes.set_xscale('linear')
            self.axes.set_yscale('linear')
        else:
            raise ValueError(self.plotTypeComboBox.currentText())

        leg = self.axes.legend(loc='best', ncol=2, fontsize='x-small')
        leg.set_visible(self.showLegendToolButton.isChecked())

        if self.showGridToolButton.isChecked():
            self.axes.grid(True, which='both')

        self.axes.set_xlabel(
            r'$q$ (nm$^{-1}$)' if self.pixelOrQToolButton.isChecked() else 'Distance from origin (pixel)')
        self.axes.set_ylabel(
            r'$d\Sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)' if self.pixelOrQToolButton.isChecked() else 'Intensity')
        # ToDo: draw logo
        if self.axes_stddev is not None:
            self.axes_stddev.set_xlabel(self.axes.get_xlabel())
            self.axes_stddev.set_ylabel('Rel. stddev. of intensity (%)')
            self.axes_stddev.grid(self.showGridToolButton.isChecked(), which='both')
        self.canvas.draw_idle()
        self.navigationToolbar.update()

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

    def clear(self):
        self.curves = []
        self.replot()

    def isPixelMode(self) -> bool:
        return not self.pixelOrQToolButton.isChecked()

    def setPixelMode(self, rawmode: bool):
        if rawmode != (not self.pixelOrQToolButton.isChecked()):
            self.pixelOrQToolButton.toggle()
        self.replot()

    def getRange(self) -> Tuple[float, float, float, float]:
        return self.axes.axis()

    def setShowErrorBars(self, show: bool):
        self.showErrorBarsToolButton.setChecked(show)

    def setSymbolsType(self, showmarkers: bool, filled: bool):
        if not showmarkers:
            self.symbolsTypeComboBox.setCurrentIndex(self.symbolsTypeComboBox.findText('No symbols'))
        elif filled:
            self.symbolsTypeComboBox.setCurrentIndex(self.symbolsTypeComboBox.findText('Filled symbols'))
        else:
            self.symbolsTypeComboBox.setCurrentIndex(self.symbolsTypeComboBox.findText('Empty symbols'))
