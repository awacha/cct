from typing import Optional

from PyQt5 import QtWidgets, QtCore

from .fsnselector_ui import Ui_Form
from ...core2.dataclasses import Exposure
from ...core2.instrument.instrument import Instrument


class FSNSelector(QtWidgets.QWidget, Ui_Form):
    fsnSelected = QtCore.pyqtSignal(str, int)

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        instrument = Instrument.instance()
        instrument.io.lastFSNChanged.connect(self.onLastFSNChanged)
        self.comboBox.addItems(sorted(instrument.io.prefixes))
        self.comboBox.currentIndexChanged.connect(self.onPrefixChanged)
        self.comboBox.setCurrentIndex(0)
        self.onPrefixChanged()
        self.spinBox.valueChanged.connect(self.onFSNSelected)
        self.firstToolButton.clicked.connect(self.gotoFirst)
        self.lastToolButton.clicked.connect(self.gotoLast)
        self.reloadToolButton.clicked.connect(self.onFSNSelected)

    def gotoFirst(self):
        self.spinBox.setValue(self.spinBox.minimum())

    def gotoLast(self):
        self.spinBox.setValue(self.spinBox.maximum())

    def setInvalid(self, invalid: bool):
        self.spinBox.setEnabled(not invalid)
        if invalid:
            self.spinBox.setRange(0, 0)
        self.firstToolButton.setEnabled(not invalid)
        self.lastToolButton.setEnabled(not invalid)
        self.reloadToolButton.setEnabled(not invalid)

    def onPrefixChanged(self):
        if self.comboBox.currentIndex() < 0:
            self.setInvalid(True)
            return
        else:
            self.setInvalid(False)
        prefix = self.comboBox.currentText()
        lastfsn = Instrument.instance().io.lastfsn(prefix)
        if lastfsn is None:
            self.setInvalid(True)
        else:
            self.setInvalid(False)
            self.spinBox.setRange(0, Instrument.instance().io.lastfsn(prefix))

    def onLastFSNChanged(self, prefix: str, fsn: int):
        if prefix == self.comboBox.currentText():
            self.spinBox.setRange(0, fsn)

    def onFSNSelected(self, value: Optional[int] = None):
        if self.comboBox.currentIndex() < 0:
            return
        self.fsnSelected.emit(
            self.comboBox.currentText(),
            value if value is not None else self.spinBox.value())

    def loadExposure(self, raw: bool = True) -> Exposure:
        return Instrument.instance().io.loadExposure(
            self.comboBox.currentText(), self.spinBox.value(), raw, check_local=True)

    def setPrefix(self, prefix: str):
        if (i := self.comboBox.findText(prefix)) >= 0:
            self.comboBox.setCurrentIndex(i)
        else:
            raise ValueError(f'Prefix {prefix} unknown.')
