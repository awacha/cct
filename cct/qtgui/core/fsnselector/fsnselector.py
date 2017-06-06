import logging
logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
from PyQt5 import QtWidgets, QtCore
from ..mixins import ToolWindow
from ....core.instrument.instrument import Instrument
from ....core.services import FileSequence
from .fsnselector_ui import Ui_Form
from sastool.classes2 import Exposure


class FSNSelector(QtWidgets.QWidget, Ui_Form, ToolWindow):
    FSNSelected = QtCore.pyqtSignal(int ,'QString', Exposure)
    horizontal = False

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)
        self._fsconnections=[]

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        if self.horizontal:
            self.hlayout = QtWidgets.QHBoxLayout()
            self.hlayout.setContentsMargins(0,0,0,0)
            self.hlayout.addWidget(self.label)
            self.hlayout.addWidget(self.prefixComboBox)
            self.hlayout.addWidget(self.label_2)
            self.hlayout.addWidget(self.FSNSpinBox)
            self.hlayout.addWidget(self.buttonContainer)
            self.hlayout.addSpacerItem(QtWidgets.QSpacerItem(0,0,QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Minimum))
            del self.formLayout
            QtWidgets.QWidget().setLayout(self.layout()) # an ugly trick to get rid of the original layout.
            self.setLayout(self.hlayout)
        self.prefixComboBox.clear()
        assert isinstance(self.credo, Instrument)
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        self.prefixComboBox.addItems(sorted(fs.get_prefixes()))
        self.prefixComboBox.setCurrentIndex(0)
        self.prefixComboBox.currentIndexChanged.connect(self.onPrefixChanged)
        self._fsconnections=[fs.connect('lastfsn-changed', self.onLastFSNChanged)]
        self.FSNSpinBox.valueChanged.connect(self.onFSNSpinBoxValueChanged)
        self.onPrefixChanged()

    def onFSNSpinBoxValueChanged(self):
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        try:
            exposure = fs.load_exposure(self.prefixComboBox.currentText(), self.FSNSpinBox.value())
            self.FSNSelected.emit(self.FSNSpinBox.value(), self.prefixComboBox.currentText(), exposure)
            del exposure
        except FileNotFoundError:
            pass

    def onLastFSNChanged(self, filesequence, prefix, lastfsn):
        if prefix != self.prefixComboBox.currentText():
            return False
        self.FSNSpinBox.setMaximum(lastfsn)
        return False

    def onPrefixChanged(self):
        self.FSNSpinBox.setMinimum(0)
        self.FSNSpinBox.setMaximum(self.credo.services['filesequence'].get_lastfsn(self.prefixComboBox.currentText()))

    def cleanup(self):
        for c in self._fsconnections:
            self.credo.services['filesequence'].disconnect(c)
        self._fsconnections=[]
        super().cleanup()

class FSNSelectorHorizontal(FSNSelector):
    horizontal = True

FSNSelectorVertical = FSNSelector