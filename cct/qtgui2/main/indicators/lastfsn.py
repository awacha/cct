from PyQt5 import QtWidgets

from .lastfsn_ui import Ui_Frame
from ....core2.instrument.instrument import Instrument


class LastFSNIndicator(QtWidgets.QFrame, Ui_Frame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Frame):
        super().setupUi(Frame)
        self.prefixComboBox.clear()
        self.prefixComboBox.addItems(sorted(Instrument.instance().io.prefixes))
        self.prefixComboBox.setCurrentIndex(0)
        Instrument.instance().io.nextFSNChanged.connect(self.onNextFSNChanged)
        Instrument.instance().io.lastFSNChanged.connect(self.onLastFSNChanged)
        Instrument.instance().scan.nextscanchanged.connect(self.onNextScanChanged)
        Instrument.instance().scan.lastscanchanged.connect(self.onLastScanChanged)
        self.nextScanLabel.setText(str(Instrument.instance().scan.nextscan()))
        self.lastScanLabel.setText(str(Instrument.instance().scan.lastscan()))
        self.prefixComboBox.currentIndexChanged.connect(self.prefixSelected)
        self.prefixSelected()

    def prefixSelected(self):
        self.nextFSNLabel.setText(str(Instrument.instance().io.nextfsn(self.prefixComboBox.currentText(), 0)))
        self.lastFSNLabel.setText(str(Instrument.instance().io.lastfsn(self.prefixComboBox.currentText())))

    def onNextFSNChanged(self, prefix, nextfsn):
        if prefix == self.prefixComboBox.currentText():
            self.nextFSNLabel.setText(str(nextfsn))

    def onLastFSNChanged(self, prefix, lastfsn):
        if prefix == self.prefixComboBox.currentText():
            self.nextFSNLabel.setText(str(lastfsn))

    def onNextScanChanged(self, nextscan):
        self.nextScanLabel.setText(str(nextscan))

    def onLastScanChanged(self, lastscan):
        self.lastScanLabel.setText(str(lastscan))
