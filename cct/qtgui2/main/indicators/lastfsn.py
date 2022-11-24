from PySide6 import QtWidgets
from PySide6.QtCore import Slot

from .lastfsn_ui import Ui_Frame
from ....core2.instrument.instrument import Instrument
from ...utils.window import WindowRequiresDevices


class LastFSNIndicator(QtWidgets.QFrame, WindowRequiresDevices, Ui_Frame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Frame):
        super().setupUi(Frame)
        self.populatePrefixComboBox()
        Instrument.instance().io.nextFSNChanged.connect(self.onNextFSNChanged)
        Instrument.instance().io.lastFSNChanged.connect(self.onLastFSNChanged)
        Instrument.instance().scan.nextscanchanged.connect(self.onNextScanChanged)
        Instrument.instance().scan.lastscanchanged.connect(self.onLastScanChanged)
        self.nextScanLabel.setText(str(Instrument.instance().scan.nextscan()))
        self.lastScanLabel.setText(str(Instrument.instance().scan.lastscan()))
        self.prefixComboBox.currentIndexChanged.connect(self.prefixSelected)
        self.prefixSelected(self.prefixComboBox.currentIndex())

    def populatePrefixComboBox(self):
        self.prefixComboBox.blockSignals(True)
        current = self.prefixComboBox.currentText()
        self.prefixComboBox.clear()
        self.prefixComboBox.addItems(sorted(Instrument.instance().io.prefixes))
        self.prefixComboBox.setCurrentIndex(self.prefixComboBox.findText(current))
        if self.prefixComboBox.currentIndex() < 0:
            self.prefixComboBox.setCurrentIndex(0)
        self.prefixComboBox.blockSignals(False)
        self.prefixSelected(self.prefixComboBox.currentIndex())

    @Slot(int)
    def prefixSelected(self, currentIndex: int):
        if self.prefixComboBox.currentIndex() < 0:
            return
        self.nextFSNLabel.setText(str(Instrument.instance().io.nextfsn(self.prefixComboBox.currentText(), 0)))
        self.lastFSNLabel.setText(str(Instrument.instance().io.lastfsn(self.prefixComboBox.currentText())))

    @Slot(str, int)
    def onNextFSNChanged(self, prefix:str, nextfsn:int):
        self.populatePrefixComboBox()
        if prefix == self.prefixComboBox.currentText():
            self.nextFSNLabel.setText(str(nextfsn))

    @Slot(str, int)
    def onLastFSNChanged(self, prefix:str, lastfsn:int):
        self.populatePrefixComboBox()
        if prefix == self.prefixComboBox.currentText():
            self.nextFSNLabel.setText(str(lastfsn))

    @Slot(int)
    def onNextScanChanged(self, nextscan:int):
        self.nextScanLabel.setText(str(nextscan))

    @Slot(int)
    def onLastScanChanged(self, lastscan:int):
        self.lastScanLabel.setText(str(lastscan))
