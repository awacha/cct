from typing import Union, Tuple, List

import numpy as np
from PyQt5 import QtWidgets
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure

from .vacuumandflux_ui import Ui_Form


class VacuumFluxViewer(QtWidgets.QWidget, Ui_Form):
    figure: Figure = None
    canvas: FigureCanvasQTAgg = None
    figToolbar: NavigationToolbar2QT = None
    axesFlux: Axes = None
    axesVacuum: Axes = None
    _samplesdists: List[Tuple[str, Union[str, float]]]

    def __init__(self, parent: QtWidgets.QWidget = None, project: "Project" = None):
        super().__init__(parent)
        self.project = project
        if self.project is None:
            raise ValueError('Vacuum and flux viewer needs a project.')
        self._samplesdists = []
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
        self.axesFlux = self.figure.add_subplot(1, 1, 1)
        self.axesVacuum = self.axesFlux.twinx()
        if self.project is not None:
            self.project.newResultsAvailable.connect(self.onNewResultsAvailable)
        self.setWindowTitle('Vacuum and flux history')

    def onNewResultsAvailable(self):
        self.replot()

    def onCanvasResize(self, event):
        pass

    def on_xscaleTypeComboBox_currentIndexChanged(self, ci: int):
        self.replot()

    def replot(self):
        vacuum = {}
        flux = {}
        enddate = {}
        for samplename, distance in self._samplesdists:
            try:
                flux.update(self.project.h5reader.getCurveParameter(samplename, distance, 'flux'))
                vacuum.update(self.project.h5reader.getCurveParameter(samplename, distance, 'vacuum'))
                enddate.update(self.project.h5reader.getCurveParameter(samplename, distance, 'enddate'))
            except KeyError:
                continue
        fsns = np.array(sorted(vacuum.keys()))
        vacuum = np.array([vacuum[fsn] for fsn in fsns])
        flux = np.array([flux[fsn] for fsn in fsns])
        enddate = [enddate[fsn] for fsn in fsns]
        if self.xscaleTypeComboBox.currentText() == 'FSN':
            x = fsns
        elif self.xscaleTypeComboBox.currentText() == 'Date':
            x = enddate
        elif self.xscaleTypeComboBox.currentText() == 'Index':
            x = np.arange(len(fsns))
        else:
            raise ValueError('Invalid x scale type: {}'.format(self.xscaleTypeComboBox.currentText()))
        self.axesFlux.clear()
        self.axesVacuum.clear()
        lines = [self.axesFlux.plot(x, flux, 'bo', label='Flux')[0],
                 self.axesVacuum.plot(x, vacuum, 'rs', label='Vacuum')[0]]
        self.axesFlux.legend(lines, [l.get_label() for l in lines], loc='best')
        self.axesFlux.set_xlabel(self.xscaleTypeComboBox.currentText())
        self.axesFlux.xaxis.set_tick_params(rotation=90 if self.xscaleTypeComboBox.currentText() == 'Date' else 0)
        self.axesFlux.set_ylabel('Flux (photons/sec)', color='b')
        self.axesVacuum.set_ylabel('Vacuum pressure (mbar)', color='r')
        meanflux = np.nanmean(flux)
        ptpflux = np.nanmax(flux) - np.nanmin(flux)

        def exponent(value):
            return int(np.floor(np.log10(np.abs(value))))

        def mantissa(value):
            return value / 10 ** exponent(value)

        self.axesFlux.set_title(
            'Mean flux: {:.3f}$\\cdot 10^{{{:d}}}$ ({:.3f}$\\cdot 10^{{{:d}}}$ ptp $\\approx$ {:.2f} %) photons/sec'.format(
                mantissa(meanflux), exponent(meanflux), mantissa(ptpflux), exponent(ptpflux), ptpflux / meanflux * 100),
            fontsize='small')
        self.canvas.draw()

    def addSampleAndDist(self, samplename: str, distance: Union[str, float], replot: bool = True):
        self._samplesdists.append((samplename, distance))
        if replot:
            self.replot()
