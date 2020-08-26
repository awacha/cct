from PyQt5 import QtWidgets

from .scanview_ui import Ui_Form
from ..utils.window import WindowRequiresDevices


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
        self.resizeTreeColumns()

    def resizeTreeColumns(self):
        for c in range(self.instrument.scan.columnCount()):
            self.treeView.resizeColumnToContents(c)

    def showScan(self):
        # ToDo
        pass