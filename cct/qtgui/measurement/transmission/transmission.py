from PyQt5 import QtWidgets, QtGui

from .transmission_ui import Ui_Form
from .transmissionmodel import TransmissionModel
from ...core.mixins import ToolWindow
from ....core.commands.transmission import Transmission
from ....core.instrument.instrument import Instrument
from ....core.instrument.privileges import PRIV_BEAMSTOP
from ....core.services.interpreter import Interpreter
from ....core.services.samples import SampleStore
from ....core.utils.inhibitor import Inhibitor


class TransmissionMeasurement(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['genix', 'pilatus', 'Motor_BeamStop_X', 'Motor_BeamStop_Y', 'Motor_Sample_X', 'Motor_Sample_Y']
    required_privilege = PRIV_BEAMSTOP

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._samplestoreconnections = []
        self._updating = Inhibitor()
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.model = TransmissionModel(None, self.credo)
        self.treeView.setModel(self.model)
        assert isinstance(self.credo, Instrument)
        ss = self.credo.services['samplestore']
        assert isinstance(ss, SampleStore)
        self._samplestoreconnections.append(
            ss.connect('list-changed', self.updateSampleComboBoxen)
        )
        self.startPushButton.clicked.connect(self.onStartClicked)
        self.cleanTablePushButton.clicked.connect(self.onCleanClicked)
        self.sampleNameComboBox.currentIndexChanged.connect(self.onSampleSelected)
        self.removeSelectedPushButton.clicked.connect(self.onRemoveSelectedSample)
        self.updateSampleComboBoxen(ss)
        self.emptyNameComboBox.setCurrentIndex(
            self.emptyNameComboBox.findText(self.credo.config['datareduction']['backgroundname']))
        self.sampleNameComboBox.setCurrentIndex(-1)
        self.adjustSize()
        for i in range(7):
            self.treeView.resizeColumnToContents(i)

    def onRemoveSelectedSample(self):
        if self.treeView.selectedIndexes():
            self.model.removeRow(self.treeView.selectedIndexes()[0].row())

    def onSampleSelected(self):
        if self._updating:
            return
        if not self.sampleNameComboBox.currentText():
            return
        self.model.add_sample(self.sampleNameComboBox.currentText())
        for i in range(7):
            self.treeView.resizeColumnToContents(i)
        with self._updating:
            self.sampleNameComboBox.setCurrentIndex(-1)

    def onStartClicked(self):
        if self.startPushButton.text() == 'Start':
            self.setBusy()
            try:
                self.executeCommand(
                    Transmission,
                    self.model.samplenames(),
                    self.nImagesSpinBox.value(),
                    self.expTimeDoubleSpinBox.value(),
                    self.emptyNameComboBox.currentText()
                )
            except:
                self.setIdle()
                raise
        else:
            assert self.startPushButton.text() == 'Stop'
            self.credo.services['interpreter'].kill()

    def onCmdReturn(self, interpreter: Interpreter, cmdname: str, retval):
        assert cmdname == 'transmission'
        super().onCmdReturn(interpreter, cmdname, retval)
        self.setIdle()

    def onCmdDetail(self, interpreter: Interpreter, cmdname: str, detail):
        what, samplename, intensity = detail
        if what == 'dark':
            self.model.update_dark(samplename, intensity)
        elif what == 'empty':
            self.model.update_empty(samplename, intensity)
        elif what == 'sample':
            self.model.update_sample(samplename, intensity)
        else:
            assert what == 'transmission'
            self.model.update_transm(samplename, intensity)
        for i in range(7):
            self.treeView.resizeColumnToContents(i)
        return False

    def setIdle(self):
        super().setIdle()
        self.startPushButton.setText('Start')
        self.startPushButton.setIcon(QtGui.QIcon.fromTheme('system-run'))
        for widget in [self.emptyNameComboBox, self.expTimeDoubleSpinBox, self.nImagesSpinBox, self.sampleNameComboBox, self.cleanTablePushButton]:
            widget.setEnabled(True)

    def setBusy(self):
        super().setBusy()
        self.startPushButton.setText('Stop')
        self.startPushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
        for widget in [self.emptyNameComboBox, self.expTimeDoubleSpinBox, self.nImagesSpinBox, self.sampleNameComboBox, self.cleanTablePushButton]:
            widget.setEnabled(False)

    def onCleanClicked(self):
        self.model = TransmissionModel(None, self.credo)
        self.treeView.setModel(self.model)

    def updateSampleComboBoxen(self, samplestore: SampleStore):
        with self._updating:
            ss = self.credo.services['samplestore']
            assert isinstance(ss, SampleStore)
            ebname = self.emptyNameComboBox.currentText()
            self.emptyNameComboBox.clear()
            self.emptyNameComboBox.addItems(sorted([sam.title for sam in ss]))
            self.emptyNameComboBox.setCurrentIndex(self.emptyNameComboBox.findText(ebname))
            self.sampleNameComboBox.clear()
            self.sampleNameComboBox.addItems(sorted([sam.title for sam in ss]))
            self.sampleNameComboBox.setCurrentIndex(-1)

    def cleanup(self):
        for c in self._samplestoreconnections:
            self.credo.services['samplestore'].disconnect(c)
        self._samplestoreconnections = []
        super().cleanup()
