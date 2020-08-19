from PyQt5 import QtWidgets, QtCore

from .fsnselector_ui import Ui_Form
from ...core2.instrument.instrument import Instrument


class FSNSelector(QtWidgets.QWidget, Ui_Form):
    fsnSelected = QtCore.pyqtSignal(str, int)

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        instrument = Instrument.instance()
        instrument.io.nextFSNChanged.connect(self.onNextFSNChanged)
        self.comboBox.addItems(sorted(instrument.io.prefixes))
        self.comboBox.currentIndexChanged.connect(self.onPrefixChanged)
        self.comboBox.setCurrentIndex(0)
        self.onPrefixChanged()
        self.spinBox.valueChanged.connect(self.onFSNSelected)

    def onPrefixChanged(self):
        prefix = self.comboBox.currentText()
        self.spinBox.setRange(0,Instrument.instance().io.lastfsn(prefix))

    def onNextFSNChanged(self, prefix:str, fsn:int):
        if prefix == self.comboBox.currentText():
            self.spinBox.setRange(0, fsn)

    def onFSNSelected(self, value):
        self.fsnSelected.emit(self.comboBox.currentText(), value)