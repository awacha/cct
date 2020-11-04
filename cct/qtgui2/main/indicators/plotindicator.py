from typing import Optional

from PyQt5 import QtWidgets

from .plotindicator_ui import Ui_Frame
from ...utils.window import WindowRequiresDevices
from ....core2.dataclasses import Exposure


class PlotIndicator(QtWidgets.QFrame, WindowRequiresDevices, Ui_Frame):
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
        finally:
            self.prefixComboBox.blockSignals(False)
        self.onPrefixChanged()

    def onLastFSNChanged(self, prefix: str, fsn: int):
        self.repopulatePrefixComboBox()
        # self.onPrefixChanged()

    def onPrefixChanged(self):
        if self.prefixComboBox.currentIndex() < 0:
            return
        self.fsnSpinBox.setRange(0, self.instrument.io.lastfsn(self.prefixComboBox.currentText()))

    def onPlotCurve(self):
        if (exposure := self.exposure()) is not None:
            self.mainwindow.showCurve(exposure)

    def onPlotImage(self):
        if (exposure := self.exposure()) is not None:
            self.mainwindow.showPattern(exposure)

    def onGoToFirstFSN(self):
        self.fsnSpinBox.setValue(self.fsnSpinBox.minimum())

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