import configparser
import inspect
import logging
import os
import pickle
from typing import Optional, Dict

import appdirs
import matplotlib.colors
import numpy as np
import pkg_resources
from PyQt5 import QtWidgets, QtCore, QtGui
from matplotlib.backend_bases import key_press_handler
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from sastool.io.credo_cct.header import Header
from scipy.misc import imread

from .backgroundtool import BackgroundTool
from .comparetool import CompareTool
from .exporttool import ExportTool
from .headerpopup import HeaderPopup
from .iotool import IoTool
from .mainwindow_ui import Ui_MainWindow
from .overalltool import OverallTool
from .persampletool import PerSampleTool
from .processingtool import ProcessingTool
from .projectdialog import ProjectDialog
from .toolbase import ToolBase, HeaderModel
from ..display import ParamPickleModel
from ..export_table import export_table
from ...core.processing.summarize import Summarizer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow, logging.Handler):
    tools: Dict[str, ToolBase] = None
    headerModel: HeaderModel = None
    h5FileName: str = None

    def __init__(self):
        QtWidgets.QMainWindow.__init__(self, None)
        logging.Handler.__init__(self, logger.level)
        self.rootdir = None
        self.processingprocess = None
        self._lastsortcolumn = 1
        self._lastsortdirection = QtCore.Qt.AscendingOrder
        self.idlefcn = None
        logging.root.addHandler(self)
        self.setupUi(self)
        self.load_state()

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        self.statusBar.showMessage(record.levelname + ': ' + msg)

    def load_state(self):
        statefile = os.path.join(appdirs.user_config_dir('cpt', 'CREDO', roaming=True), 'cpt.ini')
        config = configparser.ConfigParser()
        try:
            with open(statefile, 'rt', encoding='utf-8') as f:
                config.read_file(f)
        except FileNotFoundError:
            pass
        for t in self.tools.values():
            t.load_state(config)

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.tools['io'].autosaveProject()
        self.save_state()
        event.accept()

    def save_state(self, project=None):
        configdir = appdirs.user_config_dir('cpt', 'CREDO', roaming=True)
        os.makedirs(configdir, exist_ok=True)
        statefile = os.path.join(configdir, 'cpt.ini')
        config = configparser.ConfigParser()
        for t in self.tools:
            self.tools[t].save_state(config)
        with open(statefile, 'wt', encoding='utf-8') as f:
            config.write(f)
        logger.info('Configuration saved to {}'.format(statefile))

    def setupUi(self, MainWindow: QtWidgets.QMainWindow):
        Ui_MainWindow.setupUi(self, MainWindow)
        self.headersTreeView.header().setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.headersTreeView.header().customContextMenuRequested.connect(self.onHeaderViewHeaderContextMenu)
        self.figure = Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        vl = QtWidgets.QVBoxLayout(self.figureContainerWidget)
        vl.addWidget(self.canvas)
        self.figuretoolbar = NavigationToolbar2QT(self.canvas, self.figureContainerWidget)
        vl.addWidget(self.figuretoolbar)
        self._canvaskeypresshandler = self.canvas.mpl_connect('key_press_event', self.onCanvasKeyPressEvent)

        self.headersTreeView.header().sectionClicked.connect(self.onHeaderTreeViewSortRequest)
        self.headersTreeView.setSortingEnabled(True)
        self.headersTreeView.sortByColumn(1, QtCore.Qt.AscendingOrder)
        self.exportHeaderTablePushButton.clicked.connect(self.onExportHeadersTable)
        self.exportTablePushButton.clicked.connect(self.onExportTable)
        self.plot2DPushButton.clicked.connect(self.onPlot2D)
        self.plot1DPushButton.clicked.connect(self.onPlot1D)
        self.showMetaDataPushButton.clicked.connect(self.onShowMetaData)
        self.tablePlot1DPushButton.clicked.connect(self.onPlot1D)
        self.tablePlot2DPushButton.clicked.connect(self.onPlot2D)
        self.tools = {}
        while self.toolBox.count() > 0:
            self.toolBox.removeItem(0)
        for label, handle, type_ in [
            ('Input/output', 'io', IoTool),
            ('Sample selection', 'background', BackgroundTool),
            ('Processing', 'processing', ProcessingTool),
            ('Per-sample results', 'persample', PerSampleTool),
            ('Compare scattering curves', 'cmp', CompareTool),
            ('Overall quality checks', 'overall', OverallTool),
            ('Export', 'export', ExportTool), ]:
            self.tools[handle] = type_(self.toolBox, handle)
            self.toolBox.addItem(self.tools[handle], label)
            self.tools[handle].setFigure(self.figure)
            self.tools[handle].setTreeView(self.treeView)
            self.tools[handle].setHeadersTreeView(self.headersTreeView)
            self.tools[handle].setStatusBar(self.statusBar)
            self.tools[handle].busy.connect(self.onBusy)
            self.tools[handle].figureDrawn.connect(self.onFigureDrawn)
            self.tools[handle].tableShown.connect(self.onTableShown)
        self.toolBox.setCurrentWidget(self.tools['io'])
        self.tools['io'].h5NameChanged.connect(self.onH5NameChanged)
        self.tools['io'].newHeaderModel.connect(self.onNewHeaderModel)
        self.tools['io'].exportFolderChanged.connect(self.onExportFolderChanged)
        self.tools['io'].cctConfigChanged.connect(self.onCCTConfigChanged)
        self.tools['processing'].processingDone.connect(self.onProcessingDone)
        self.projectdialog = ProjectDialog(self)
        self.projectdialog.projectSelected.connect(self.onProjectSelected)
        self.projectdialog.show()
        self.hide()

    def onProjectSelected(self, projectname):
        self.tools['io'].loadProject(projectname)
        self.show()

    def onBusy(self, busy: bool):
        self.setEnabled(not busy)

    def onProcessingDone(self):
        self.tools['io'].h5NameChanged.emit(self.tools['io'].h5FileName)
        self.tools['io'].autosaveProject()

    def onFigureDrawn(self):
        self.putlogo()
        self.canvas.draw()
        self.tabWidget.setCurrentWidget(self.figureContainerWidget)

    def onTableShown(self):
        for c in range(self.treeView.model().columnCount()):
            self.treeView.resizeColumnToContents(c)
        self.tabWidget.setCurrentWidget(self.tableContainerWidget)

    def onCCTConfigChanged(self, cctConfig: Dict):
        self.cctConfig = cctConfig
        for t in self.tools:
            self.tools[t].setCCTConfig(cctConfig)

    def onExportFolderChanged(self, exportfolder: str):
        for t in self.tools:
            self.tools[t].setExportFolder(exportfolder)

    def onNewHeaderModel(self, headerModel: HeaderModel):
        self.headerModel = headerModel
        self.headersTreeView.setSortingEnabled(False)
        self.headersTreeView.setModel(headerModel)
        self.headersTreeView.setSortingEnabled(True)
        self.headersTreeView.sortByColumn(self._lastsortcolumn, self._lastsortdirection)
        self.resizeHeaderViewColumns()
        self.updateTimeLabels()
        for h in self.tools:
            self.tools[h].setHeaderModel(headerModel)
        self.statusBar.clearMessage()

    def onH5NameChanged(self, h5name: str):
        for h in self.tools:
            self.tools[h].setH5FileName(h5name)
        self.h5FileName = h5name
        self.updateTimeLabels()
        self.statusBar.clearMessage()

    def onCanvasKeyPressEvent(self, event):
        key_press_handler(event, self.canvas, self.figuretoolbar)

    def onShowMetaData(self):
        idx = self.headersTreeView.currentIndex()
        if not idx.isValid():
            return
        fsn = self.headersTreeView.model().getFSN(idx)
        for pth in self.headerModel.eval2d_pathes:
            try:
                fname = os.path.join(
                    pth,
                    '{{}}_{{:0{:d}d}}.pickle'.format(
                        self.cctConfig['path']['fsndigits']).format(
                        self.cctConfig['path']['prefixes']['crd'], fsn))
                with open(fname, 'rb') as f:
                    metadata = pickle.load(f)
                model = ParamPickleModel(self.treeView)
                model.setParamPickle(metadata)
                self.treeView.setModel(model)
                # self.treeView.expandAll()
                self.tabWidget.setCurrentWidget(self.tableContainerWidget)
                for c in range(2):
                    self.treeView.resizeColumnToContents(c)
                break
            except (FileNotFoundError, OSError):
                continue

    def onHeaderTreeViewSortRequest(self, section: int):
        self.headersTreeView.setSortingEnabled(True)
        if section == self._lastsortcolumn:
            if self._lastsortdirection == QtCore.Qt.AscendingOrder:
                self._lastsortdirection = QtCore.Qt.DescendingOrder
            else:
                self._lastsortdirection = QtCore.Qt.AscendingOrder
        else:
            self._lastsortcolumn = section
            self._lastsortdirection = QtCore.Qt.AscendingOrder
        print('Lastsortcolumn: {} lastsortdirection: {}'.format(self._lastsortcolumn, self._lastsortdirection), )
        self.headersTreeView.sortByColumn(self._lastsortcolumn, self._lastsortdirection)

    def onExportHeadersTable(self):
        fname, fltr = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Write table to file...', '',
            'MS Excel 2007-2016 files (*.xlsx, *.xlsm);;MS Excel files (*.xls);;All files (*)',
            'MS Excel 2007-2016 files (*.xlsx, *.xlsm)')
        if not fname:
            return
        export_table(fname, self.headerModel)
        logger.info('Wrote file {}'.format(fname))

    def onExportTable(self):
        fname, fltr = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Write table to file...', '',
            'MS Excel 2007-2016 files (*.xlsx, *.xlsm);;MS Excel files (*.xls);;All files (*)',
            'MS Excel 2007-2016 files (*.xlsx, *.xlsm)')
        if not fname:
            return
        export_table(fname, self.treeView.model())
        logger.info('Wrote file {}'.format(fname))

    def resizeHeaderViewColumns(self):
        for i in range(self.headerModel.columnCount()):
            self.headersTreeView.resizeColumnToContents(i)

    def onHeaderViewHeaderContextMenu(self, position: QtCore.QPoint):
        self.headerpopup = HeaderPopup(
            self, self.headerModel.visiblecolumns,
            sorted([x[0] for x in inspect.getmembers(Header) if isinstance(x[1], property)]))
        self.headerpopup.applied.connect(self.onHeaderPopupApplied)
        self.headerpopup.show()
        self.headerpopup.move(self.mapToGlobal(position))
        self.headerpopup.closed.connect(self.onHeaderPopupDestroyed)
        self.resizeHeaderViewColumns()

    def onHeaderPopupDestroyed(self):
        del self.headerpopup

    def onHeaderPopupApplied(self):
        self.headerModel.visiblecolumns = self.headerpopup.fields
        self.header_columns = self.headerpopup.fields
        self.tools['io'].reloadHeaders()

    def updateTimeLabels(self):
        if self.headerModel is None:
            return
        totaltime = self.headerModel.totalExperimentTime()
        for labelwidget, timedelta in [
            (self.totalExperimentTimeLabel, self.headerModel.totalExperimentTime()),
            (self.goodExposureTimeLabel, self.headerModel.netGoodExposureTime()),
            (self.badExposureTimeLabel, self.headerModel.netBadExposureTime()),
            (self.netExposureTimeLabel, self.headerModel.netExposureTime()),
            (self.deadTimeLabel, self.headerModel.totalExperimentTime() - self.headerModel.netExposureTime()),
        ]:
            time_h = np.floor(timedelta / 3600)
            time_min = np.floor(timedelta - time_h * 3600) / 60
            time_sec = np.floor(timedelta - time_h * 3600 - time_min * 60)
            labelwidget.setText('{:02.0f}:{:02.0f}:{:02.0f} ({:.1f}%)'.format(
                time_h, time_min, time_sec, timedelta / totaltime * 100))

    def putlogo(self, figure: Optional[Figure] = None):
        if figure is None:
            figure = self.figure
        if not hasattr(self, '_logodata'):
            self._logodata = imread(pkg_resources.resource_filename('cct', 'resource/credo_logo.png'), flatten=True)[
                             ::4, ::4]
        figure.figimage(self._logodata, 10, 10, cmap='gray', zorder=-10)

    def onPlot1D(self):
        if self.sender() == self.plot1DPushButton:
            treeview = self.headersTreeView
        elif self.sender() == self.tablePlot1DPushButton:
            treeview = self.treeView
        else:
            return
        idx = treeview.currentIndex()
        if not idx.isValid():
            return
        try:
            fsn = treeview.model().getFSN(idx)
        except AttributeError:
            return
        summarizer = Summarizer([fsn], self.headerModel.eval2d_pathes, self.headerModel.eval2d_pathes,
                                self.headerModel.mask_pathes, self.h5FileName,
                                self.cctConfig['path']['prefixes']['crd'],
                                self.cctConfig['path']['fsndigits'])
        for x in summarizer.load_headers():
            pass
        ex = summarizer.load_exposure(fsn)
        self.figure.clear()
        ax = self.figure.add_subplot(1, 1, 1)
        ex.radial_average().loglog(axes=ax)
        ax.set_xlabel('q (nm$^{-1}$)')
        ax.set_ylabel('Intensity (cm$^{-1}$ sr$^{-1}$)')
        self.onFigureDrawn()

    def onPlot2D(self):
        if self.sender() == self.plot2DPushButton:
            treeview = self.headersTreeView
        elif self.sender() == self.tablePlot2DPushButton:
            treeview = self.treeView
        else:
            return
        idx = treeview.currentIndex()
        if not idx.isValid():
            return
        try:
            fsn = treeview.model().getFSN(idx)
        except AttributeError:
            return
        summarizer = Summarizer([fsn], self.headerModel.eval2d_pathes, self.headerModel.eval2d_pathes,
                                self.headerModel.mask_pathes, self.h5FileName,
                                self.cctConfig['path']['prefixes']['crd'],
                                self.cctConfig['path']['fsndigits'])
        for x in summarizer.load_headers(logger=logger):
            pass
        ex = summarizer.load_exposure(fsn, logger=logger)
        self.figure.clear()
        ax = self.figure.add_subplot(1, 1, 1)
        ex.imshow(axes=ax, norm=matplotlib.colors.LogNorm())
        ax.set_xlabel('q (nm$^{-1}$)')
        ax.set_ylabel('q (nm$^{-1}$)')
        self.onFigureDrawn()
