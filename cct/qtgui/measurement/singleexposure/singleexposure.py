from PyQt5 import QtWidgets, QtGui

from .singleexposure_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.commands.detector import Expose, ExposeMulti
from ....core.commands.motor import SetSample
from ....core.commands.xray_source import Shutter
from ....core.services.exposureanalyzer import ExposureAnalyzer
from ....core.services.filesequence import FileSequence
from ....core.services.interpreter import Interpreter


class SingleExposure(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['genix', 'pilatus']

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo)
        self._failed = False
        self._fsconnections = []
        self._eaconnections = []
        self.setupUi(self)

    def cleanup(self):
        for c in self._fsconnections:
            self.credo.services['filesequence'].disconnect(c)
        self._fsconnections = []
        for c in self._eaconnections:
            self.credo.services['exposureanalyzer'].disconnect(c)
        self._eaconnections = []
        super().cleanup()

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.progressBar.setVisible(False)
        self.prefixComboBox.currentIndexChanged.connect(self.onPrefixChanged)
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        ea = self.credo.services['exposureanalyzer']
        assert isinstance(ea, ExposureAnalyzer)
        self.prefixComboBox.addItems(fs.get_prefixes())
        self.prefixComboBox.setCurrentIndex(self.prefixComboBox.findText('tst'))
        self.onPrefixChanged()
        fs.connect('nextfsn-changed', self.onNextFSNChanged)
        ea.connect('image', self.onImage)

    def onImage(self):
        pass

    def onNextFSNChanged(self, fs: FileSequence, prefix: str, nextfsn: int):
        self.onPrefixChanged()
        return False

    def onPrefixChanged(self):
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        self.nextFSNLabel.setText(str(fs.get_nextfreefsn(self.prefixComboBox.currentText(), False)))

    def onExpose(self):
        if self.exposePushButton.text() == 'Expose':
            self.setBusy()
            if self.sampleNameCheckBox.isChecked():
                self.executeCommand(SetSample, self.sampleNameComboBox.currentText())
            else:
                self.onCmdReturn(self.credo.services['interpreter'], 'sample', None)
        else:
            self.credo.services['interpreter'].kill()

    def onCmdReturn(self, interpreter: Interpreter, cmdname: str, retval):
        super().onCmdReturn(interpreter, cmdname, retval)
        if self._failed:
            if cmdname != 'shutter':
                if self.autoShutterCheckBox.isChecked():
                    # try to close shutter and return
                    self.executeCommand(Shutter, False)
                else:
                    # only simulate the closure of the shutter
                    self.onCmdReturn(interpreter, 'shutter', False)
            else:
                # if the Shutter command failed, do nothing
                self.setIdle()
        if cmdname == 'shutter' and not retval:
            self.setIdle()
        elif cmdname == 'shutter' and retval:
            # start the exposure
            if self.nImagesSpinBox.value() > 1:
                self.executeCommand(ExposeMulti, self.expTimeDoubleSpinBox.value(),
                                    self.nImagesSpinBox.value(),
                                    self.prefixComboBox.currentText(),
                                    self.delayDoubleSpinBox.value())
            else:
                self.executeCommand(Expose, self.expTimeDoubleSpinBox.value(),
                                    self.prefixComboBox.currentText())
        elif cmdname == 'sample':
            # open shutter if needed
            if self.autoShutterCheckBox.isChecked():
                self.executeCommand(Shutter, True)
            else:
                self.onCmdReturn(interpreter, 'shutter', True)

    def onCmdFail(self, interpreter: Interpreter, cmdname: str, exception: Exception, traceback: str):
        self._failed = True

    def setIdle(self):
        super().setIdle()
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/exposure.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.exposePushButton.setIcon(icon)
        self.exposePushButton.setText('Expose')

    def setBusy(self):
        super().setBusy()
        self.exposePushButton.setText('Stop')
        self.exposePushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
        self.entryWidget.setEnabled(False)
