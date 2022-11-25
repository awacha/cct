from typing import Optional

from PySide6 import QtWidgets
from PySide6.QtCore import Slot

from .plotindicator_ui import Ui_Frame
from ...utils.window import WindowRequiresDevices
from ....core2.dataclasses import Exposure


class PlotIndicator(WindowRequiresDevices, QtWidgets.QFrame, Ui_Frame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Frame):
        super().setupUi(Frame)
        self.instrument.io.lastFSNChanged.connect(self.onLastFSNChanged)
        self.prefixComboBox.currentIndexChanged.connect(self.onPrefixChanged)
        self.plotCurveToolButton.clicked.connect(self.onPlotCurve)
        self.plotImageToolButton.clicked.connect(self.onPlotImage)
        self.firstFSNTtoolButton.clicked.connect(self.onGoToFirstFSN)
        self.lastFSNToolButton.clicked.connect(self.onGoToLastFSN)
        self.fsnSpinBox.setRange(0, 0)
        self.fsnSpinBox.setEnabled(False)
        self.repopulatePrefixComboBox()

    def repopulatePrefixComboBox(self):
        current = self.prefixComboBox.currentText()
        self.prefixComboBox.blockSignals(True)
        try:
            self.prefixComboBox.clear()
            self.prefixComboBox.addItems(sorted(self.instrument.io.prefixes))
            self.prefixComboBox.setCurrentIndex(self.prefixComboBox.findText(current))
            if self.prefixComboBox.currentIndex() < 0:
                self.prefixComboBox.setCurrentIndex(0)
            self.fsnSpinBox.setEnabled(self.prefixComboBox.currentIndex() >= 0)
            self.plotCurveToolButton.setEnabled(self.prefixComboBox.currentIndex() >= 0)
            self.plotImageToolButton.setEnabled(self.prefixComboBox.currentIndex() >= 0)
        finally:
            self.prefixComboBox.blockSignals(False)
        self.onPrefixChanged(self.prefixComboBox.currentIndex())

    @Slot(str, int)
    def onLastFSNChanged(self, prefix: str, fsn: int):
        self.repopulatePrefixComboBox()
        # self.onPrefixChanged()

    @Slot(int)
    def onPrefixChanged(self, currentIndex:int):
        if self.prefixComboBox.currentIndex() < 0:
            return
        self.fsnSpinBox.setEnabled(self.prefixComboBox.currentIndex() >= 0)
        self.plotCurveToolButton.setEnabled(self.prefixComboBox.currentIndex() >= 0)
        self.plotImageToolButton.setEnabled(self.prefixComboBox.currentIndex() >= 0)
        lastfsn = self.instrument.io.lastfsn(self.prefixComboBox.currentText())
        self.fsnSpinBox.setRange(0, -1 if lastfsn is None else lastfsn)

    @Slot()
    def onPlotCurve(self):
        if (exposure := self.exposure()) is not None:
            self.mainwindow.showCurve(exposure)

    @Slot()
    def onPlotImage(self):
        if (exposure := self.exposure()) is not None:
            self.mainwindow.showPattern(exposure)

    @Slot()
    def onGoToFirstFSN(self):
        self.fsnSpinBox.setValue(self.fsnSpinBox.minimum())

    @Slot()
    def onGoToLastFSN(self):
        self.fsnSpinBox.setValue(self.fsnSpinBox.maximum())

    def exposure(self) -> Optional[Exposure]:
        try:
            return self.instrument.io.loadExposure(prefix=self.prefixComboBox.currentText(),
                                                   fsn=self.fsnSpinBox.value(), check_local=True)
        except FileNotFoundError as fnfe:
            QtWidgets.QMessageBox.critical(
                self, 'Error',
                f'Cannot load exposure {self.prefixComboBox.currentText()}/#{self.fsnSpinBox.value()}: {fnfe}')
        return None
