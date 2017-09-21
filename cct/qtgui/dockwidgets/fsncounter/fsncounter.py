from PyQt5 import QtWidgets

from .fsncounter_ui import Ui_DockWidget
from ...core.mixins import ToolWindow
from ....core.services.filesequence import FileSequence


class FSNCounter(QtWidgets.QDockWidget, Ui_DockWidget, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QDockWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._fs_connections = []
        self.setupUi(self)

    def setupUi(self, DockWidget):
        assert not self._fs_connections
        Ui_DockWidget.setupUi(self, DockWidget)
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        self._fs_connections = [fs.connect('nextfsn-changed', self.onNextFSNChanged),
                                fs.connect('nextscan-changed', self.onNextScanChanged),
                                fs.connect('lastfsn-changed', self.onLastFSNChanged),
                                fs.connect('lastscan-changed', self.onLastScanChanged),
                                ]
        self.prefixComboBox.addItems(sorted(fs.get_prefixes()))
        self.prefixComboBox.currentIndexChanged.connect(self.onPrefixChanged)
        self.prefixComboBox.setCurrentIndex(0)
        prefix = self.prefixComboBox.currentText()
        self.lastPrefixLabel.setText(prefix)
        self.lastPrefixLastLabel.setText(str(fs.get_lastfsn(prefix)))
        self.lastPrefixNextLabel.setText(str(fs.get_nextfreefsn(prefix, False)))
        self.onPrefixChanged()

    def onPrefixChanged(self):
        fs = self.credo.services['filesequence']
        prefix = self.prefixComboBox.currentText()
        self.selectedPrefixNextLabel.setText(str(fs.get_nextfreefsn(prefix, False)))
        self.selectedPrefixLastLabel.setText(str(fs.get_lastfsn(prefix)))

    def onNextFSNChanged(self, filesequence, prefix, nextfsn):
        if self.lastPrefixLabel.text() != prefix:
            self.lastPrefixLabel.setText(prefix)
            fs = self.credo.services['filesequence']
            assert isinstance(fs, FileSequence)
            self.lastPrefixLastLabel.setText(str(fs.get_lastfsn(prefix)))
        self.lastPrefixNextLabel.setText(str(nextfsn))
        if self.prefixComboBox.currentText() == prefix:
            self.selectedPrefixNextLabel.setText(str(nextfsn))

    def onLastFSNChanged(self, filesequence, prefix, lastfsn):
        if self.lastPrefixLabel.text() != prefix:
            self.lastPrefixLabel.setText(prefix)
            fs = self.credo.services['filesequence']
            assert isinstance(fs, FileSequence)
            self.lastPrefixNextLabel.setText(fs.get_nextfreefsn(prefix, acquire=False))
        self.lastPrefixLastLabel.setText(str(lastfsn))
        if self.prefixComboBox.currentText() == prefix:
            self.selectedPrefixLastLabel.setText(str(lastfsn))

    def onNextScanChanged(self, filesequence, nextscan):
        pass

    def onLastScanChanged(self, filesequence, lastscan):
        pass

    def cleanup(self):
        super().cleanup()
        for c in self._fs_connections:
            self.credo.services['filesequence'].disconnect(c)
        self._fs_connections = []
