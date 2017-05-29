from PyQt5 import QtWidgets, QtCore, QtGui
from sastool.io.credo_cct import Exposure, Header

from .datareduction_ui import Ui_Form
from ...core.exposuremodel import HeaderModel
from ...core.mixins import ToolWindow
from ....core.services.exposureanalyzer import ExposureAnalyzer


class DataReduction(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo)
        self._currentfsn = None
        self._ea_connection = []
        self._stoprequested = False
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.firstFSNSpinBox.valueChanged.connect(self.onFirstFSNChanged)
        self.lastFSNSpinBox.valueChanged.connect(self.onLastFSNChanged)
        self.model = HeaderModel(None, self.credo, self.credo.config['path']['prefixes']['crd'], self.firstFSNSpinBox.value(), self.lastFSNSpinBox.value())
        self.treeView.setModel(self.model)
        self.reloadHeaders()
        self.reloadPushButton.clicked.connect(self.reloadHeaders)
        self.startStopPushButton.clicked.connect(self.onStartReduction)
        self.treeView.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.progressBar.setVisible(False)

    def onSelectionChanged(self):
        self.startStopPushButton.setEnabled(bool(self.selectedFSNs()))

    def onStartReduction(self):
        if self.startStopPushButton.text()=='Reduce selected exposures':
            self.setBusy()
            self._stoprequested = False
            self.submitNextFSN()
        else:
            self._stoprequested = True

    def submitNextFSN(self):
        ea = self.credo.services['exposureanalyzer']
        assert isinstance(ea, ExposureAnalyzer)
        try:
            self._currentfsn=self.selectedFSNs()[0]
        except IndexError:
            self._currentfsn = None
            self.setIdle()
            return
        prefix=self.credo.config['path']['prefixes']['crd']
        header = self.model.header(self._currentfsn)
        assert isinstance(header, Header)
        ea.submit(
            self._currentfsn,
            self.credo.services['filesequence'].exposurefileformat(prefix,self._currentfsn)+'.cbf',
            prefix,
            param=header._data)
        self.treeView.selectionModel().select(
            self.model.index(self.model.rowForFSN(self._currentfsn),0),
            QtCore.QItemSelectionModel.Current | QtCore.QItemSelectionModel.Rows
        )

    def setBusy(self):
        super().setBusy()
        ea=self.credo.services['exposureanalyzer']
        assert isinstance(ea, ExposureAnalyzer)
        assert not self._ea_connection
        self._ea_connection=[ea.connect('datareduction-done', self.reducingDone)]
        self.inputWidget.setEnabled(False)
        self.startStopPushButton.setText('Stop data reduction')
        self.startStopPushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
        self.progressBar.setVisible(True)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(len(self.selectedFSNs()))
        self.progressBar.setValue(0)

    def cleanup(self):
        for c in self._ea_connection:
            self.credo.services['exposureanalyzer'].disconnect(c)
        self._ea_connection=[]
        super().cleanup()

    def setIdle(self):
        super().setIdle()
        for c in self._ea_connection:
            self.credo.services['exposureanalyzer'].disconnect(c)
        self._ea_connection=[]
        self.inputWidget.setEnabled(True)
        self.startStopPushButton.setText('Reduce selected exposures')
        self.startStopPushButton.setIcon(QtGui.QIcon.fromTheme('system-run'))
        self.progressBar.setVisible(False)

    def selectedFSNs(self):
        return sorted(set([self.model.createIndex(idx.row(), 0).data(QtCore.Qt.DisplayRole)
                for idx in self.treeView.selectedIndexes()]))

    def reducingDone(self, ea:ExposureAnalyzer, prefix:str, fsn:int, ex:Exposure):
        if self._currentfsn != fsn:
            return False
        if self._stoprequested:
            self.setIdle()
            return False
        self.treeView.selectionModel().select(
            self.model.index(self.model.rowForFSN(fsn),0),
            QtCore.QItemSelectionModel.Deselect | QtCore.QItemSelectionModel.Rows
        )
        self.submitNextFSN()
        self.progressBar.setValue(self.progressBar.value()+1)

    def onFirstFSNChanged(self):
        self.lastFSNSpinBox.setMinimum(self.firstFSNSpinBox.value())

    def onLastFSNChanged(self):
        self.firstFSNSpinBox.setMaximum(self.lastFSNSpinBox.value())

    def reloadHeaders(self):
        self.model.fsnfirst=self.firstFSNSpinBox.value()
        self.model.fsnlast=self.lastFSNSpinBox.value()
        self.model.reloadHeaders()