from typing import Optional

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Signal, Slot

from .fsnselector_ui import Ui_Form
from ...core2.dataclasses import Exposure
from ...core2.instrument.instrument import Instrument


class FSNSelector(QtWidgets.QWidget, Ui_Form):
    fsnSelected = Signal(str, int)
    horizontal: bool=True

    def __init__(self, parent: QtWidgets.QWidget, horizontal: bool=True):
        super().__init__(parent)
        self.horizontal = horizontal
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        if not self.horizontal:
            self.horizontalLayout.removeWidget(self.comboBox)
            self.horizontalLayout.removeWidget(self.reloadToolButton)
            self.horizontalLayout.removeItem(self.horizontalLayout_2)
            self.horizontalLayout.removeWidget(self.label)
            self.horizontalLayout.removeWidget(self.label_2)
            grid: QtWidgets.QGridLayout = QtWidgets.QGridLayout(self)
            self.horizontalLayout.addLayout(grid, 1)
            grid.addWidget(self.label, 0, 0, 1, 1)
            grid.addWidget(self.comboBox, 0, 1, 1, 1)
            grid.addWidget(self.label_2, 1, 0, 1, 1)
            grid.addLayout(self.horizontalLayout_2, 1, 1, 1, 1)
            grid.addWidget(self.reloadToolButton, 0, 2, 1, 1)
            self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)

        instrument = Instrument.instance()
        instrument.io.lastFSNChanged.connect(self.onLastFSNChanged)
        self.comboBox.addItems(sorted(instrument.io.prefixes))
        self.comboBox.currentIndexChanged.connect(self.onPrefixChanged)
        self.comboBox.setCurrentIndex(0)
        self.onPrefixChanged(self.comboBox.currentIndex())
        self.spinBox.valueChanged.connect(self.onFSNSelected)
        self.firstToolButton.clicked.connect(self.gotoFirst)
        self.lastToolButton.clicked.connect(self.gotoLast)
        self.reloadToolButton.clicked.connect(self.onReloadClicked)

    @Slot(bool)
    def onReloadClicked(self, checked: bool):
        self.onLastFSNChanged(self.comboBox.currentIndex(), self.spinBox.value())

    @Slot()
    def gotoFirst(self):
        self.spinBox.setValue(self.spinBox.minimum())

    @Slot()
    def gotoLast(self):
        self.spinBox.setValue(self.spinBox.maximum())

    def setInvalid(self, invalid: bool):
        self.spinBox.setEnabled(not invalid)
        if invalid:
            self.spinBox.setRange(0, 0)
        self.firstToolButton.setEnabled(not invalid)
        self.lastToolButton.setEnabled(not invalid)
        self.reloadToolButton.setEnabled(not invalid)

    @Slot(int)
    def onPrefixChanged(self, index:int):
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

    @Slot(str, int)
    def onLastFSNChanged(self, prefix: str, fsn: int):
        if prefix == self.comboBox.currentText():
            self.spinBox.setRange(0, fsn)

    @Slot(int)
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

    def prefix(self) -> str:
        return self.comboBox.currentText()

    def fsn(self) -> int:
        return self.spinBox.value()