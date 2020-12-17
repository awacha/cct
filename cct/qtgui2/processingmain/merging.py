from typing import Optional
import logging

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.widgets import SpanSelector

from .processingwindow import ProcessingWindow
from .merging_ui import Ui_Form

from PyQt5 import QtGui, QtWidgets, QtCore

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MergingWindow(ProcessingWindow, Ui_Form):
    canvas: FigureCanvasQTAgg
    figure: Figure
    axes: Axes
    figtoolbar: NavigationToolbar2QT
    spanSelector: Optional[SpanSelector]

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.project.merging)
        self.addPushButton.clicked.connect(self.addSample)
        self.runPushButton.clicked.connect(self.runClicked)
        self.removePushButton.clicked.connect(self.removeSample)
        self.project.merging.dataChanged.connect(self.resizeTreeViewColumns)
        self.project.merging.modelReset.connect(self.resizeTreeViewColumns)
        self.project.merging.started.connect(self.onMergingStarted)
        self.project.merging.finished.connect(self.onMergingStopped)
        self.project.merging.progress.connect(self.onProgress)
        self.progressBar.setVisible(False)
        self.figure = Figure(constrained_layout=True, figsize=(3,4))
        self.axes = self.figure.add_subplot(self.figure.add_gridspec(1,1)[:,:])
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figtoolbar = NavigationToolbar2QT(self.canvas, self)
        self.figureVerticalLayout.addWidget(self.figtoolbar)
        self.figureVerticalLayout.addWidget(self.canvas, 1)
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self._resetaxes()
        self.canvas.draw_idle()
        self.treeView.selectionModel().selectionChanged.connect(self.onSelectionChanged)

    def onSelectionChanged(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection):
        self._resetaxes()
        try:
            index = self.treeView.selectionModel().selectedRows(0)[0]
        except IndexError:
            self.canvas.draw_idle()
            return
        sampleindex = index
        while sampleindex.parent().isValid():
            sampleindex = index.parent()
        samplename = sampleindex.data(QtCore.Qt.DisplayRole)
        if index.parent().isValid():
            selecteddistkey = index.data(QtCore.Qt.DisplayRole)
        else:
            selecteddistkey = None
        for i, distkey in enumerate(sorted(self.project.settings.h5io.distancekeys(samplename), key= lambda k:float(k))):
            curve = self.project.settings.h5io.readCurve(f'Samples/{samplename}/{distkey}/curve')
            ebar = self.axes.errorbar(curve.q, curve.intensity, curve.uncertainty, curve.quncertainty, lw = 2 if distkey == selecteddistkey else 0.7, label=f'{distkey} mm', zorder=100 if distkey==selecteddistkey else 10)
            qmin, qmax = self.treeView.model().index(i, 1, sampleindex).data(QtCore.Qt.EditRole), self.treeView.model().index(i, 2, sampleindex).data(QtCore.Qt.EditRole)
            logger.debug(f'{qmin=}, {qmax=}')
            self.axes.axvspan(qmin, qmax, color=ebar[0].get_color(), alpha=0.3 if distkey == selecteddistkey else 0.1)
        self.axes.legend(loc='best')
        self.axes.set_title(samplename)
        if selecteddistkey is not None:
            self.spanSelector = SpanSelector(self.axes, self.onSpanSelected, direction='horizontal', useblit=True)
        else:
            self.spanSelector = None
        self.canvas.draw_idle()

    def onSpanSelected(self, left: float, right: float):
        try:
            index = self.treeView.selectionModel().selectedRows(0)[0]
        except IndexError:
            # should not happen, but who knows...
            return
        if not index.parent().isValid():
            # this is a top-level index. This should not happen, but who knows...
            return
        else:
            parent = index.parent()
            row = index.row()
            self.treeView.model().setData(self.treeView.model().index(row, 1, parent), left, QtCore.Qt.EditRole)
            self.treeView.model().setData(self.treeView.model().index(row, 2, parent), right, QtCore.Qt.EditRole)

    def _resetaxes(self):
        self.axes.clear()
        self.axes.grid(True, which='both')
        self.axes.set_xscale('log')
        self.axes.set_yscale('log')
        self.axes.set_xlabel('$q$ (nm$^{-1}$)')
        self.axes.set_ylabel('Intensity')

    def addSample(self):
        samplename, ok = QtWidgets.QInputDialog.getItem(
            self,
            'Select a sample',
            'Sample name:',
            sorted([sn for sn in self.project.settings.h5io.samplenames() if sn not in self.project.merging]), 0, editable=False, )
        if ok:
            self.project.merging.addSample(samplename)
            self.treeView.expandAll()
            self.resizeTreeViewColumns()

    def removeSample(self):
        samples = []
        for index in self.treeView.selectionModel().selectedRows(column=0):
            while index.parent().isValid():
                index = index.parent()
            samples.append(index.data(QtCore.Qt.DisplayRole))
        for sample in samples:
            self.project.merging.removeSample(sample)

    def resizeTreeViewColumns(self):
        for c in range(self.treeView.model().columnCount(QtCore.QModelIndex())):
            self.treeView.resizeColumnToContents(c)

    def runClicked(self):
        if self.runPushButton.text() == 'Run':
            self.project.merging.start()
        else:
            self.project.merging.stop()

    def onMergingStarted(self):
        self.runPushButton.setText('Stop')
        self.runPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/stop.svg')))
        self.progressBar.setVisible(True)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)

    def onMergingStopped(self, success: bool):
        self.runPushButton.setText('Run')
        self.runPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
        self.progressBar.setVisible(False)
        if not success:
            QtWidgets.QMessageBox.critical(self, 'Merging stopped', 'Merging stopped unexpectedly.')

    def onProgress(self, current: int, total: int):
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(current)
