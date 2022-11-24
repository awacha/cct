from typing import Optional

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSlot as Slot

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
        self.showPushButton.clicked.connect(self.onShowPushButtonClicked)
        self.treeView.activated.connect(self.showScan)
        self.resizeTreeColumns()

    @Slot()
    def resizeTreeColumns(self):
        for c in range(self.instrument.scan.columnCount()):
            self.treeView.resizeColumnToContents(c)

    @Slot(bool)
    def onShowPushButtonClicked(self, checked: bool):
        self.showScan(self.treeView.currentIndex())

    @Slot(QtCore.QModelIndex)
    def showScan(self, index: QtCore.QModelIndex):
        scan = index.data(QtCore.Qt.ItemDataRole.UserRole)
        assert isinstance(scan, Scan)
        plotscan = self.mainwindow.addSubWindow(PlotScan, singleton=False)
        plotscan.setScan(scan)
