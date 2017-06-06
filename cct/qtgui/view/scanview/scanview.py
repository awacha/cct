from PyQt5 import QtCore, QtWidgets

from .scanstore import ScanModel
from .scanview_ui import Ui_Form
from ...core.mixins import ToolWindow
from ...core.scangraph import ScanGraph
from ....core.instrument.instrument import Instrument
from ....core.services.filesequence import FileSequence


class ScanViewer(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self,*args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        assert isinstance(self.credo, Instrument)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        assert isinstance(self.credo, Instrument)
        fs=self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        self.scanModel=ScanModel(None, self.credo, fs.get_scanfile())
        self.scanFileComboBox.addItems(fs.get_scanfiles())
        self.treeView.setModel(self.scanModel)
        self.scanFileComboBox.currentTextChanged.connect(self.onScanFileSelected)
        self.reloadPushButton.clicked.connect(self.onReload)
        for c in range(self.scanModel.columnCount()):
            self.treeView.resizeColumnToContents(c)
        self.treeView.doubleClicked.connect(self.onDoubleClicked)
        self.showPushButton.clicked.connect(self.onShowClicked)

    def onShowClicked(self):
        return self.onDoubleClicked(self.treeView.selectionModel().selectedRows()[0])

    def onScanFileSelected(self):
        self.scanModel.setScanFile(self.scanFileComboBox.currentText())
        for c in range(self.scanModel.columnCount()):
            self.treeView.resizeColumnToContents(c)

    def onReload(self):
        self.scanModel.setScanFile(self.scanFileComboBox.currentText())
        for c in range(self.scanModel.columnCount()):
            self.treeView.resizeColumnToContents(c)

    def onDoubleClicked(self, index:QtCore.QModelIndex):
        scanindex = self.scanModel.data(self.scanModel.index(index.row(), 0), QtCore.Qt.DisplayRole)
        assert isinstance(self.credo, Instrument)
        fs=self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        scan = fs.load_scan(scanindex, self.scanModel.scanfile)
        sg = ScanGraph(credo=self.credo)
        sg.setWindowTitle('Scan #{:d}'.format(scanindex))
        sg.setCurve(scan['data'], len(scan['data']))
        sg.show()
