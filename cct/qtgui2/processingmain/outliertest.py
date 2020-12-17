import logging
import itertools
from typing import Tuple, List

import numpy as np
import scipy.stats.kde
from PyQt5 import QtWidgets, QtCore
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
import matplotlib.cm
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.backend_bases import PickEvent

from .outliertest_ui import Ui_Form
from .resultviewwindow import ResultViewWindow
from .showimage import ShowImageWindow
from .showcurve import ShowCurveWindow
from ..utils.plotcurve import PlotCurve
from ...core2.dataclasses import Header
from ...core2.processing.calculations.outliertest import OutlierTest

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SortFilterModel(QtCore.QSortFilterProxyModel):
    samplename: str
    distkey: str

    def __init__(self, samplename: str, distkey: str):
        self.samplename = samplename
        self.distkey = distkey
        super().__init__()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        data = self.sourceModel().index(source_row, 0, source_parent).data(QtCore.Qt.UserRole)
        assert isinstance(data, Header)
        return (data.title == self.samplename) and (f'{data.distance[0]:.2f}' == self.distkey)

    def filterAcceptsColumn(self, source_column: int, source_parent: QtCore.QModelIndex) -> bool:
        caption = self.sourceModel().headerData(source_column, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
        return caption in ['fsn', 'enddate']


class OutlierTestWindow(ResultViewWindow, Ui_Form):
    outliertestresults : OutlierTest
    cmatfigure: Figure
    cmatcanvas: FigureCanvasQTAgg
    cmatfigtoolbar: NavigationToolbar2QT
    cmataxes: Axes
    otfigure: Figure
    otcanvas: FigureCanvasQTAgg
    otfigtoolbar: NavigationToolbar2QT
    otaxes: Axes
    otkdeaxes: Axes
    sortfiltermodel: SortFilterModel
    plotcurve: PlotCurve
    otmarkedline: Line2D
    cmatmarkers: List[Line2D]


    def setupUi(self, Form):
        super().setupUi(Form)
        self.project.results.modelReset.connect(self.redraw)
        self.cmatfigure = Figure(figsize=(5, 3), constrained_layout=True)
        self.cmatcanvas = FigureCanvasQTAgg(self.cmatfigure)
        self.cmatcanvas.mpl_connect('pick_event', self.cmatPicked)
        self.cmatfigtoolbar = NavigationToolbar2QT(self.cmatcanvas, self.correlMatrixTab)
        self.correlMatrixTab.setLayout(QtWidgets.QVBoxLayout())
        self.correlMatrixTab.layout().addWidget(self.cmatfigtoolbar)
        self.correlMatrixTab.layout().addWidget(self.cmatcanvas, 1)
        self.cmataxes = self.cmatfigure.add_subplot(self.cmatfigure.add_gridspec(1, 1)[:, :])
        self.otfigure = Figure(figsize=(5, 3), constrained_layout=True)
        self.otcanvas = FigureCanvasQTAgg(self.otfigure)
        self.otcanvas.mpl_connect('pick_event', self.otPicked)
        self.otfigtoolbar = NavigationToolbar2QT(self.otcanvas, self.outlierTestTab)
        self.outlierTestTab.setLayout(QtWidgets.QVBoxLayout())
        self.outlierTestTab.layout().addWidget(self.otfigtoolbar)
        self.outlierTestTab.layout().addWidget(self.otcanvas)
        self.plotcurve = PlotCurve(self.curvesTab)
        self.curvesTab.setLayout(QtWidgets.QVBoxLayout())
        self.curvesTab.layout().addWidget(self.plotcurve)
        gs = self.otfigure.add_gridspec(1, 8)
        self.otaxes = self.otfigure.add_subplot(gs[:, :-1])
        self.otkdeaxes = self.otfigure.add_subplot(gs[:, -1], sharey=self.otaxes)
        self.sortfiltermodel = SortFilterModel(self.samplename, self.distancekey)
        self.sortfiltermodel.setSourceModel(self.project.headers)
        self.treeView.setModel(self.sortfiltermodel)
        for col in range(self.sortfiltermodel.columnCount(QtCore.QModelIndex())):
            self.treeView.resizeColumnToContents(col)
        self.reloadPushButton.clicked.connect(self.project.headers.start)
        self.showCurvePushButton.clicked.connect(self.showCurve)
        self.showImagePushButton.clicked.connect(self.showImage)
        self.treeView.selectionModel().selectionChanged.connect(self.fsnSelectionChanged)
        self.onResultItemChanged(self.samplename, self.distancekey)
        self.markBadPushButton.clicked.connect(self.markExposures)
        self.markGoodPushButton.clicked.connect(self.markExposures)

    def markExposures(self):
        fsns = [index.data(QtCore.Qt.UserRole).fsn for index in self.treeView.selectionModel().selectedRows(0)]
        if self.sender() is self.markBadPushButton:
            self.project.settings.markAsBad(fsns)
        elif self.sender() is self.markGoodPushButton:
            self.project.settings.markAsGood(fsns)

    def redraw(self):
        self.cmatfigure.clear()
        self.cmataxes = self.cmatfigure.add_subplot(self.cmatfigure.add_gridspec(1, 1)[:, :])
        im = self.cmataxes.imshow(self.outliertestresults.correlmatrix, cmap='coolwarm', interpolation='nearest', origin='upper', picker=5)
        self.cmatfigure.colorbar(im, ax=self.cmataxes)
        self.cmataxes.set_xticks(np.arange(len(self.outliertestresults.fsns)))
        self.cmataxes.set_xticklabels([str(f) for f in self.outliertestresults.fsns], rotation=90)
        self.cmataxes.set_yticks(np.arange(len(self.outliertestresults.fsns)))
        self.cmataxes.set_yticklabels([str(f) for f in self.outliertestresults.fsns])
        self.cmataxes.set_title(f'{self.samplename} @ {self.distancekey} mm')
        self.otaxes.clear()
        rmin, rmax = self.outliertestresults.acceptanceInterval()
        self.otaxes.axhspan(rmin, rmax, color='lightgreen', alpha=0.5)
        self.otaxes.axhline(rmin, color='lightgreen', ls='--')
        self.otaxes.axhline(rmax, color='lightgreen', ls='--')
        self.otaxes.plot(self.outliertestresults.fsns, self.outliertestresults.score, 'b.', pickradius=5, picker=True)
        self.otaxes.set_title(f'{self.samplename} @ {self.distancekey} mm')
        self.otmarkedline = self.otaxes.scatter(self.outliertestresults.fsns, self.outliertestresults.score, [0.0]*len(self.outliertestresults.fsns), c='none', edgecolors='red')
        self.otkdeaxes.clear()
        kde = scipy.stats.kde.gaussian_kde(self.outliertestresults.score)
        y = np.linspace(min(np.nanmin(self.outliertestresults.score) - np.ptp(self.outliertestresults.score) * 0.1, rmin),
                        max(np.nanmax(self.outliertestresults.score) + np.ptp(self.outliertestresults.score), rmax), 300)
        self.otkdeaxes.plot(kde(y), y)
        self.otkdeaxes.set_xlabel('Gaussian KDE')
        self.otkdeaxes.yaxis.set_label_position('right')
        self.otkdeaxes.yaxis.set_ticks_position('right')
        self.otaxes.set_xlabel('File sequence number')
        self.otaxes.set_ylabel('Outlier score')
        self.otcanvas.draw()
        self.cmatcanvas.draw()
        self.setWindowTitle(f'Outlier test results for {self.samplename} @ {self.distancekey} mm')
        self.plotcurve.clear()
        self.plotcurve.setShowErrorBars(False)
        self.plotcurve.setPixelMode(False)
        self.cmatmarkers = []
        curves = self.project.settings.h5io.readCurves(f'Samples/{self.samplename}/{self.distancekey}')
        for i, fsn in enumerate(sorted(curves)):
            self.plotcurve.addCurve(curves[fsn], label=f'{fsn}', color=matplotlib.cm.inferno(i/(len(curves)-1)))
        self.plotcurve.replot()

    def showImage(self):
        for index in self.treeView.selectionModel().selectedRows(0):
            header = index.data(QtCore.Qt.UserRole)
            samplename = header.title
            distkey = f'{header.distance[0]:.2f}'
            self.mainwindow.createViewWindow(
                ShowImageWindow(
                    project=self.project, mainwindow=self.mainwindow,
                    samplename=samplename, distancekey=distkey, closable=True),
                handlestring=f"ShowImage(samplename='{samplename}', distancekey='{distkey}')")

    def showCurve(self):
        fsns = sorted([index.data(QtCore.Qt.UserRole).fsn for index in self.treeView.selectionModel().selectedRows(0)])
        scw = ShowCurveWindow(
                project=self.project, mainwindow=self.mainwindow,
                resultitems=[], closable=True)
        plottedcurves = []
        for fsn in fsns:
            for curvesgroupname in ['allcurves', 'curves']:
                try:
                    scw.plotCurve.addCurve(self.project.settings.h5io.readCurve(f'Samples/{self.samplename}/{self.distancekey}/{curvesgroupname}/{fsn}'), label=f'#{fsn}')
                    plottedcurves.append(fsn)
                    break
                except KeyError:
                    continue
            else:
                continue
                #QtWidgets.QMessageBox.critical(self, 'Curve not found', f'Curve for FSN {fsn} not found.')
        if not plottedcurves:
            scw.destroy(True, True)
            return
        scw.plotCurve.replot()
        self.mainwindow.createViewWindow(
            scw,
            handlestring=f"ShowCurve(fsns={fsns})")

    def onResultItemChanged(self, samplename: str, distkey: str):
        self.outliertestresults = self.project.settings.h5io.readOutlierTest(f'Samples/{self.samplename}/{self.distancekey}')
        self.redraw()

    @property
    def samplename(self) -> str:
        return self.resultitems[0][0]

    @property
    def distancekey(self) -> str:
        return self.resultitems[0][1]

    def otPicked(self, event: PickEvent):
        logger.debug(event.artist)
        logger.debug(dir(event))
        logger.debug(f'{event.ind=}, {event.guiEvent=}, {event.name=}')
        pickedindex = event.ind[0]
        fsn = event.artist.get_xdata()[pickedindex]
        for row in range(self.treeView.model().rowCount(QtCore.QModelIndex())):
            index = self.treeView.model().index(row, 0, QtCore.QModelIndex())
            if self.treeView.model().data(index, QtCore.Qt.UserRole).fsn == fsn:
                if self.treeView.selectionModel().isRowSelected(row, QtCore.QModelIndex()):
                    self.treeView.selectionModel().select(index, QtCore.QItemSelectionModel.Rows | QtCore.QItemSelectionModel.Deselect)
                else:
                    self.treeView.selectionModel().select(index, QtCore.QItemSelectionModel.Rows | QtCore.QItemSelectionModel.Select)

    def cmatPicked(self, event: PickEvent):
        logger.debug([event.mouseevent.xdata, event.mouseevent.ydata])
        col = int(round(event.mouseevent.xdata))
        row = int(round(event.mouseevent.ydata))
        for i in {row, col}:
            fsn = self.outliertestresults.fsns[i]
            for row in range(self.treeView.model().rowCount(QtCore.QModelIndex())):
                index = self.treeView.model().index(row, 0, QtCore.QModelIndex())
                if self.treeView.model().data(index, QtCore.Qt.UserRole).fsn == fsn:
                    if self.treeView.selectionModel().isRowSelected(row, QtCore.QModelIndex()):
                        self.treeView.selectionModel().select(index, QtCore.QItemSelectionModel.Rows | QtCore.QItemSelectionModel.Deselect)
                    else:
                        self.treeView.selectionModel().select(index, QtCore.QItemSelectionModel.Rows | QtCore.QItemSelectionModel.Select)

    def fsnSelectionChanged(self, selected, deselected):
        selectedfsns = [index.data(QtCore.Qt.UserRole).fsn for index in self.treeView.selectionModel().selectedRows(0)]
        sizes = self.otmarkedline.get_sizes()
        for i in range(sizes.size):
            sizes[i] = 0 if self.outliertestresults.fsns[i] not in selectedfsns else 100
        self.otmarkedline.set_sizes(sizes)
        self.otcanvas.draw_idle()
        for line in self.cmatmarkers:
            line.remove()
        self.cmatmarkers = []
        for fsn in selectedfsns:
            try:
                index = [i for i in range(self.outliertestresults.fsns.size) if self.outliertestresults.fsns[i] == fsn][0]
            except IndexError:
                continue
            self.cmatmarkers.append(self.cmataxes.axhline(index, color='black', ls='--'))
            self.cmatmarkers.append(self.cmataxes.axvline(index, color='black', ls='--'))
        self.cmatcanvas.draw_idle()

