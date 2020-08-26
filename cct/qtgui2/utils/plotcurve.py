import logging
from typing import Dict, Any, Tuple, List

from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure
from sastool.classes2 import Curve

from .plotcurve_ui import Ui_Form

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class PlotCurve(QtWidgets.QWidget, Ui_Form):
    curves: List[Tuple[Curve, Dict[str, Any], bool, bool]] = None
    figure: Figure
    axes: Axes
    canvas: FigureCanvasQTAgg
    navigationToolbar: NavigationToolbar2QT
    MARKERS: str = 'ovsp*D^h<H>x+d1234'
    _figsize: Tuple[float, float] = None

    def __init__(self, parent: QtWidgets.QWidget = None, figsize: Tuple[float, float] = (6, 6)):
        super().__init__(parent)
        self._figsize = figsize
        self.curves = []
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(figsize=self._figsize, constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.navigationToolbar = NavigationToolbar2QT(self.canvas, self)
        self.axes = self.figure.add_subplot(1, 1, 1)
        self.figureVerticalLayout.addWidget(self.navigationToolbar)
        self.figureVerticalLayout.addWidget(self.canvas)

    def addCurve(self, curve: Curve, xraw: bool, yraw: bool, **kwargs):
        assert isinstance(curve, Curve)
        curve = curve.sanitize()
        self.curves.append((curve, kwargs, xraw, yraw))
        logger.debug('Curve elements types: q: {}, Intensity: {}, Error: {}, qError: {}'.format(type(curve.q),
                                                                                                type(curve.Intensity),
                                                                                                type(curve.Error),
                                                                                                type(curve.qError)))
        logger.debug('Added a curve.')

    def on_plotTypeComboBox_currentIndexChanged(self):
        self.replot()

    def on_showErrorBarsToolButton_toggled(self):
        self.replot()

    def on_showGridToolButton_toggled(self):
        self.axes.grid(self.showGridToolButton.isChecked(), which='both')
        self.canvas.draw()

    def on_showLegendToolButton_toggled(self):
        self.axes.get_legend().set_visible(self.showLegendToolButton.isChecked())
        self.canvas.draw()

    def on_showLinesToolButton_toggled(self):
        self.replot()

    def on_symbolsTypeComboBox_currentIndexChanged(self):
        self.replot()

    def replot(self):
        logger.debug('Replotting curves')
        self.figure.clear()
        self.axes = self.figure.add_subplot(1, 1, 1)
        for i, (curve, kwargs) in enumerate(self.curves):
            if curve is None:
                # curve is temporarily absent.
                continue
            kwargs = kwargs.copy()  # do not change the original
            x = curve.q
            y = curve.Intensity
            dx = curve.qError
            dy = curve.Error
            if self.plotTypeComboBox.currentText() == 'Kratky':
                dy = ((curve.q ** 2 * curve.Error) ** 2 + (2 * curve.Intensity * curve.q * curve.qError) ** 2) ** 0.5
                y = curve.Intensity * curve.q ** 2
            elif self.plotTypeComboBox.currentText() == 'Porod':
                dy = ((curve.q ** 4 * curve.Error) ** 2 + (
                        4 * curve.Intensity * curve.q ** 3 * curve.qError) ** 2) ** 0.5
                y = curve.Intensity * curve.q ** 4
            else:
                # do nothing
                pass
            if self.showLinesToolButton.isChecked():
                # force drawing a line
                kwargs.setdefault('linestyle', '-')
                if not kwargs['linestyle']:
                    # if it is an empty string (as given by the user)
                    kwargs['linestyle'] = '-'
            else:
                # hide the line
                kwargs['linestyle'] = ''
            if self.symbolsTypeComboBox.currentText() == 'No symbols':
                # force hiding symbols
                kwargs['marker'] = ''
            else:
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
            self.axes.set_xscale('guinierq')
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

        self.axes.set_xlabel(r'$q$ (nm$^{-1}$)')
        self.axes.set_ylabel(r'$d\Sigma/d\Omega$ (cm$^{-1}$ sr$^{-1}$)')
        # ToDo: draw logo
        self.canvas.draw()
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

    def isRawMode(self) -> bool:
        return not self.plotTypeComboBox.isVisible()

    def setRawMode(self, rawmode: bool):
        self.plotTypeComboBox.setVisible(not rawmode)
        self.replot()