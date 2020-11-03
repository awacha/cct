from PyQt5 import QtWidgets

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
        self.prefixSelected()

    def populatePrefixComboBox(self):
        self.prefixComboBox.blockSignals(True)
        current = self.prefixComboBox.currentText()
        self.prefixComboBox.clear()
        self.prefixComboBox.addItems(sorted(Instrument.instance().io.prefixes))
        self.prefixComboBox.setCurrentIndex(self.prefixComboBox.findText(current))
        if self.prefixComboBox.currentIndex() < 0:
            self.prefixComboBox.setCurrentIndex(0)
        self.prefixComboBox.blockSignals(False)
        self.prefixSelected()

    def prefixSelected(self):
        if self.prefixComboBox.currentIndex() < 0:
            return
        self.nextFSNLabel.setText(str(Instrument.instance().io.nextfsn(self.prefixComboBox.currentText(), 0)))
        self.lastFSNLabel.setText(str(Instrument.instance().io.lastfsn(self.prefixComboBox.currentText())))

    def onNextFSNChanged(self, prefix, nextfsn):
        self.populatePrefixComboBox()
        if prefix == self.prefixComboBox.currentText():
            self.nextFSNLabel.setText(str(nextfsn))

    def onLastFSNChanged(self, prefix, lastfsn):
        self.populatePrefixComboBox()
        if prefix == self.prefixComboBox.currentText():
            self.nextFSNLabel.setText(str(lastfsn))

    def onNextScanChanged(self, nextscan):
        self.nextScanLabel.setText(str(nextscan))

    def onLastScanChanged(self, lastscan):
        self.lastScanLabel.setText(str(lastscan))
