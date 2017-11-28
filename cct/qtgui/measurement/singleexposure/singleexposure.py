import logging

import numpy as np
from PyQt5 import QtWidgets, QtGui
from sastool.io.credo_cct import Exposure, Header

from .singleexposure_ui import Ui_Form
from ...core.mixins import ToolWindow
from ...core.plotimage import PlotImage
from ....core.commands.detector import Expose, ExposeMulti
from ....core.commands.motor import SetSample
from ....core.commands.xray_source import Shutter
from ....core.services.exposureanalyzer import ExposureAnalyzer
from ....core.services.filesequence import FileSequence
from ....core.services.interpreter import Interpreter
from ....core.services.samples import SampleStore

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SingleExposure(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['genix', 'pilatus']

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._failed = False
        self._fsconnections = []
        self._eaconnections = []
        self._samconnections = []
        self._image_expected = False
        self.setupUi(self)

    def cleanup(self):
        for c in self._fsconnections:
            self.credo.services['filesequence'].disconnect(c)
        self._fsconnections = []
        for c in self._eaconnections:
            self.credo.services['exposureanalyzer'].disconnect(c)
        self._eaconnections = []
        for c in self._samconnections:
            self.credo.services['samplestore'].disconnect(c)
        self._samconnections = []
        self._image_expected = False
        super().cleanup()

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.progressBar.setVisible(False)
        self.prefixComboBox.currentIndexChanged.connect(self.onPrefixChanged)
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        ea = self.credo.services['exposureanalyzer']
        assert isinstance(ea, ExposureAnalyzer)
        sams = self.credo.services['samplestore']
        assert isinstance(sams, SampleStore)
        self.prefixComboBox.addItems(fs.get_prefixes())
        self.prefixComboBox.setCurrentIndex(self.prefixComboBox.findText('tst'))
        self.onPrefixChanged()
        self._fsconnections = [fs.connect('nextfsn-changed', self.onNextFSNChanged)]
        self._eaconnections = [ea.connect('image', self.onImage)]
        self._samconnections = [sams.connect('list-changed', self.onSampleListChanged)]
        self.onSampleListChanged(sams)
        self.exposePushButton.clicked.connect(self.onExpose)
        self.adjustSize()

    def onSampleListChanged(self, samplestore: SampleStore):
        currentsample = self.sampleNameComboBox.currentText()
        self.sampleNameComboBox.clear()
        self.sampleNameComboBox.addItems([s.title for s in samplestore.get_samples()])
        idx = self.sampleNameComboBox.findText(currentsample)
        if idx < 0:
            idx = self.sampleNameComboBox.findText(samplestore.get_active_name())
        self.sampleNameComboBox.setCurrentIndex(idx)

    def onImage(self, ea: ExposureAnalyzer, prefix: str, fsn: int, image: np.ndarray, params: dict, mask: np.ndarray):
        if not self._image_expected:
            return False
        logger.debug('Image received.')
        pi = PlotImage.get_lastinstance()
        if pi is None:
            pi = PlotImage()
        ex = Exposure(image, None, Header(params), mask)
        pi.setExposure(ex)
        pi.show()
        self._image_expected = False
        return False

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
        logger.debug('Command {} finished with {}'.format(cmdname, retval))
        super().onCmdReturn(interpreter, cmdname, retval)
        if cmdname == 'shutter' and retval is None:
            retval = self.credo.get_device('genix').get_variable('shutter')
        if self._failed:
            logger.debug('Command {} failed!!!'.format(cmdname))
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
            logger.debug('Starting the exposure')
            if self.nImagesSpinBox.value() > 1:
                self.executeCommand(ExposeMulti, self.expTimeDoubleSpinBox.value(),
                                    self.nImagesSpinBox.value(),
                                    self.prefixComboBox.currentText(),
                                    self.delayDoubleSpinBox.value())
            else:
                self.executeCommand(Expose, self.expTimeDoubleSpinBox.value(),
                                    self.prefixComboBox.currentText())
            self._image_expected = True
        elif cmdname == 'sample':
            # open shutter if needed
            logger.debug('Sample in place.')
            if self.autoShutterCheckBox.isChecked():
                self.executeCommand(Shutter, True)
            else:
                self.onCmdReturn(interpreter, 'shutter', True)
        elif cmdname.startswith('expose'):
            if self.autoShutterCheckBox.isChecked():
                self.executeCommand(Shutter, False)
            else:
                self.onCmdReturn(interpreter, 'shutter', False)

    def onCmdFail(self, interpreter: Interpreter, cmdname: str, exception: Exception, traceback: str):
        self._failed = True

    def setIdle(self):
        super().setIdle()
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/exposure.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.exposePushButton.setIcon(icon)
        self.exposePushButton.setText('Expose')
        self.entryWidget.setEnabled(True)

    def setBusy(self):
        super().setBusy()
        self.exposePushButton.setText('Stop')
        self.exposePushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
        self.entryWidget.setEnabled(False)
