from PyQt5 import QtWidgets
from .resultviewwindow import ResultViewWindow
from .vacuum_ui import Ui_Form
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.axes import Axes

import logging
logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class VacuumWindow(ResultViewWindow, Ui_Form):
    figure: Figure
    canvas: FigureCanvasQTAgg
    figtoolbar: NavigationToolbar2QT
    axesvacuum: Axes
    axesflux: Axes

    def setupUi(self, Form):
        super().setupUi(self)
        self.figure = Figure(constrained_layout=True, figsize=(4,3))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figtoolbar = NavigationToolbar2QT(self.canvas, self)
        self.axesvacuum = self.figure.add_subplot(self.figure.add_gridspec(1,1)[:,:])
        self.axesflux = self.axesvacuum.twinx()
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(self.figtoolbar)
        layout.addWidget(self.canvas, stretch=1)
        self.onResultItemChanged('', '')

    def onResultItemChanged(self, samplename: str, distancekey: str):
        dates = []
        flux = []
        vacuum = []
        for samplename, distancekey in self.resultitems:
            sde = self.project.results.get(samplename, distancekey)
            headers = sde.headers(all=True)
            dates.extend([headers[fsn].enddate for fsn in sorted(headers)])
            flux.extend([headers[fsn].flux for fsn in sorted(headers)])
            vacuum.extend([headers[fsn].vacuum for fsn in sorted(headers)])
        logger.debug(str(dates))
        self.axesvacuum.clear()
        self.axesvacuum.plot(dates, [v[0] for v in vacuum], 'bo')
        self.axesflux.plot(dates, [f[0] for f in flux], 'rs')
        self.axesvacuum.set_xlabel('Date of measurement')
        self.axesvacuum.set_ylabel('Vacuum (mbar)', color='b')
        self.axesflux.set_ylabel('Flux (photons/sec)', color='r')
        self.axesvacuum.set_xlim(min(dates), max(dates))
        self.axesvacuum.xaxis.set_tick_params(labelrotation=90)
        self.axesvacuum.yaxis.set_tick_params(colors='b')
        self.axesflux.yaxis.set_tick_params(colors='r')
        self.canvas.draw_idle()
