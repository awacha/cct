from typing import Optional

from PyQt5 import QtWidgets, QtCore

from .scanview_ui import Ui_Form
from ..utils.plotscan import PlotScan
from ..utils.window import WindowRequiresDevices
from ...core2.dataclasses import Scan


class ScanViewer(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.scan)
        self.instrument.scan.rowsInserted.connect(self.resizeTreeColumns)
        self.instrument.scan.modelReset.connect(self.resizeTreeColumns)
        self.showPushButton.clicked.connect(self.showScan)
        self.treeView.activated.connect(self.showScan)
        self.resizeTreeColumns()

    def resizeTreeColumns(self):
        for c in range(self.instrument.scan.columnCount()):
            self.treeView.resizeColumnToContents(c)

    def showScan(self, index: Optional[QtCore.QModelIndex] = None):
        if not isinstance(index, QtCore.QModelIndex):
            index = self.treeView.currentIndex()
        scan = index.data(QtCore.Qt.UserRole)
        assert isinstance(scan, Scan)
        plotscan = self.mainwindow.addSubWindow(PlotScan, singleton=False)
        plotscan.setScan(scan)
