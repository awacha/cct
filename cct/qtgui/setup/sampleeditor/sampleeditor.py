import datetime
import logging
import re

from PyQt5 import QtWidgets, QtCore, QtGui

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from .sampleeditor_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.services.samples import Sample, SampleStore
from ....core.services.accounting import Accounting, Project
from ....core.utils.inhibitor import Inhibitor


class SampleEditor(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._updating_entries = Inhibitor()
        self._samplestoreconnections = []
        self._selectedsample = None
        self._accountingconnections = []
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.onSampleListChanged(self.credo.services['samplestore'])
        self.listWidget.itemSelectionChanged.connect(self.onSelectionChanged)
        self.sampleNameLineEdit.setValidator(
            QtGui.QRegularExpressionValidator(QtCore.QRegularExpression('[-A-Za-z0-9_]+')))
        self.addSamplePushButton.clicked.connect(self.onAddSample)
        self.removeSamplePushButton.clicked.connect(self.onRemoveSample)
        self.duplicateSamplePushButton.clicked.connect(self.onDuplicateSample)
        self._samplestoreconnections = [
            self.credo.services['samplestore'].connect('list-changed', self.onSampleListChanged)]
        self._accountingconnections = [
            self.credo.services['accounting'].connect('project-changed', self.onProjectListChanged),
        ]
        self.onSelectionChanged()
        for lineedit in [self.preparedByLineEdit, self.maskOverrideLineEdit]:
            lineedit.textEdited.connect(self.onTextEdited)
        self.descriptionPlainTextEdit.textChanged.connect(self.onTextEdited)
        for spinbox in [self.transmissionErrDoubleSpinBox, self.transmissionValDoubleSpinBox,
                        self.thicknessErrDoubleSpinBox, self.thicknessValDoubleSpinBox, self.distminusErrDoubleSpinBox,
                        self.distminusValDoubleSpinBox, self.xPositionErrDoubleSpinBox, self.xPositionValDoubleSpinBox,
                        self.yPositionErrDoubleSpinBox, self.yPositionValDoubleSpinBox]:
            spinbox.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
        for combobox in [self.categoryComboBox, self.situationComboBox, self.projectComboBox]:
            combobox.currentTextChanged.connect(self.onComboBoxChanged)
        self.calendarWidget.selectionChanged.connect(self.onCalendarChanged)
        self.onProjectListChanged(self.credo.services['accounting'])
        self.todayPushButton.clicked.connect(self.onTodayClicked)
        self.sampleNameLineEdit.installEventFilter(self)
        self.maskOverridePushButton.clicked.connect(self.browseForMask)
        self.maskOverrideCheckBox.clicked.connect(self.maskOverrideChanged)

    def maskOverrideChanged(self):
        if self.maskOverrideCheckBox.isChecked():
            self.maskOverrideLineEdit.setText(self.credo.config['geometry']['mask'])
        else:
            self.maskOverrideLineEdit.setText('')
        self.maskOverrideLineEdit.textEdited.emit(self.maskOverrideLineEdit.text())

    def browseForMask(self):
        filename, filter = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Open mask file...', self.credo.config['path']['directories']['mask'], '*.mat',
        )
        if filename:
            self.maskOverrideLineEdit.setText(filename)
            self.maskOverrideCheckBox.setChecked(True)
            self.maskOverrideLineEdit.textEdited.emit(filename)

    def eventFilter(self, obj:QtCore.QObject, event:QtCore.QEvent):
        if obj is self.sampleNameLineEdit and isinstance(event, QtGui.QFocusEvent):
            if event.lostFocus():
                logger.debug('Sample name editor has lost focus.')
                self.onRenameSample()
        return super().eventFilter(obj, event)

    def onTodayClicked(self):
        if self._updating_entries:
            return
        selectedsamplename = self.selectedSampleName()
        if selectedsamplename is None:
            return
        sample = self.credo.services['samplestore'].get_sample(selectedsamplename)
        sample.preparetime=datetime.datetime.now()
        self.credo.services['samplestore'].set_sample(selectedsamplename, sample)
        self.selectSample(sample.title)

    def selectedSampleName(self):
        try:
            return self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
        except IndexError:
            return None

    def onProjectListChanged(self, accounting:Accounting):
        current = self.projectComboBox.currentData()
        self.projectComboBox.blockSignals(True)
        try:
            self.projectComboBox.clear()
            self.projectComboBox.addItem('-- Unassigned --', userData=None)
            for i,p in enumerate(sorted(accounting.projects, key=lambda p:p.projectid)):
                assert isinstance(p, Project)
                self.projectComboBox.addItem('{}: {}'.format(p.projectid, p.projectname), userData=p.projectid)
            index=self.projectComboBox.findData(current)
            self.projectComboBox.setCurrentIndex(index)
        finally:
            self.projectComboBox.blockSignals(False)
        if index<0:
            self.projectComboBox.setCurrentIndex(0)

    def onRenameSample(self):
        ss = self.credo.services['samplestore']
        assert isinstance(ss, SampleStore)
        try:
            sample = ss.get_sample(self.sampleNameLineEdit.text())
            if sample is self._selectedsample:
                # avoid error if renaming the selected sample to the same name.
                raise KeyError
        except KeyError:
            # this is normal.
            sample = Sample(ss.get_sample(self.selectedSampleName()))
            sample.title = self.sampleNameLineEdit.text()
            ss.set_sample(self.selectedSampleName(), sample)
            self.selectSample(sample.title)
        else:
            QtWidgets.QMessageBox.critical(self, 'Invalid sample name', 'Another sample already exists with this name.')
            return

    def onTextEdited(self, newtext=None):
        if self._updating_entries:
            return
        selectedsamplename = self.selectedSampleName()
        if selectedsamplename is None:
            return
        sample = self.credo.services['samplestore'].get_sample(selectedsamplename)
        if self.sender() == self.sampleNameLineEdit:
            sample.title = self.sampleNameLineEdit.text()
        elif self.sender() == self.preparedByLineEdit:
            sample.preparedby = self.preparedByLineEdit.text()
        elif self.sender() == self.descriptionPlainTextEdit:
            sample.description = self.descriptionPlainTextEdit.toPlainText()
        elif self.sender() == self.maskOverrideLineEdit:
            sample.maskoverride = self.maskOverrideLineEdit.text() if self.maskOverrideCheckBox.isChecked() else None
            logger.debug('Maskoverride for sample {} changed to: {}'.format(sample.title, sample.maskoverride))
        else:
            assert False
        self.credo.services['samplestore'].set_sample(selectedsamplename, sample)
        self.selectSample(sample.title)

    def onDoubleSpinBoxValueChanged(self, newvalue):
        if self._updating_entries:
            return
        selectedsamplename = self.selectedSampleName()
        if selectedsamplename is None:
            return
        sample = self.credo.services['samplestore'].get_sample(selectedsamplename)
        if self.sender() == self.distminusErrDoubleSpinBox:
            sample.distminus.err = self.sender().value()
        elif self.sender() == self.distminusValDoubleSpinBox:
            sample.distminus.val = self.sender().value()
        elif self.sender() == self.thicknessErrDoubleSpinBox:
            sample.thickness.err = self.sender().value()
        elif self.sender() == self.thicknessValDoubleSpinBox:
            sample.thickness.val = self.sender().value()
        elif self.sender() == self.transmissionErrDoubleSpinBox:
            sample.transmission.err = self.sender().value()
        elif self.sender() == self.transmissionValDoubleSpinBox:
            sample.transmission.val = self.sender().value()
        elif self.sender() == self.xPositionErrDoubleSpinBox:
            sample.positionx.err = self.sender().value()
        elif self.sender() == self.xPositionValDoubleSpinBox:
            sample.positionx.val = self.sender().value()
        elif self.sender() == self.yPositionErrDoubleSpinBox:
            sample.positiony.err = self.sender().value()
        elif self.sender() == self.yPositionValDoubleSpinBox:
            sample.positiony.val = self.sender().value()
        else:
            assert False
        self.credo.services['samplestore'].set_sample(selectedsamplename, sample)
        self.selectSample(sample.title)

    def onComboBoxChanged(self):
        if self._updating_entries:
            return
        selectedsamplename = self.selectedSampleName()
        if selectedsamplename is None:
            return
        sample = self.credo.services['samplestore'].get_sample(selectedsamplename)
        if self.sender() == self.categoryComboBox:
            sample.category = self.categoryComboBox.currentText()
        elif self.sender() == self.situationComboBox:
            sample.situation = self.situationComboBox.currentText()
        elif self.sender() == self.projectComboBox:
            sample.project = self.projectComboBox.currentData()
            if not sample.project:
                sample.project=None
            if self.projectComboBox.currentIndex()<0:
                self.projectComboBox.setCurrentIndex(0)
        else:
            assert False
        self.credo.services['samplestore'].set_sample(selectedsamplename, sample)
        self.selectSample(sample.title)

    def onCalendarChanged(self):
        if self._updating_entries:
            return
        selectedsamplename = self.selectedSampleName()
        if selectedsamplename is None:
            return
        sample = self.credo.services['samplestore'].get_sample(selectedsamplename)
        if self.sender() == self.calendarWidget:
            sample.preparetime = datetime.datetime.fromordinal(
                self.calendarWidget.selectedDate().toPyDate().toordinal())
        else:
            assert False
        self.credo.services['samplestore'].set_sample(selectedsamplename, sample)
        self.selectSample(sample.title)

    def onAddSample(self):
        samplestore = self.credo.services['samplestore']
        assert isinstance(samplestore, SampleStore)
        sampletitle = 'Unnamed'
        index = 0
        while not samplestore.add(Sample(sampletitle)):
            index += 1
            sampletitle = 'Unnamed_{:d}'.format(index)
        self.selectSample(sampletitle)

    def onRemoveSample(self):
        selectedsamplename = self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
        samplestore = self.credo.services['samplestore']
        sample = samplestore.get_sample(selectedsamplename)
        if sample.preparedby == 'SYSTEM':
            QtWidgets.QMessageBox.critical(self, 'Cannot delete sample', 'Cannot delete "SYSTEM" sample.')
            return
        assert isinstance(samplestore, SampleStore)
        samplenames = [s.title for s in samplestore]
        # we will activate the previous sample in the list
        prevsample = samplenames[max(0, samplenames.index(selectedsamplename) - 1)]
        if prevsample == selectedsamplename:
            # this happens when we are trying to remove the first sample in the list
            try:
                prevsample = samplenames[1]
            except IndexError:
                # this happens when there is only one sample left in the samplestore and we want
                # to delete that. This is not possible, since there should always be an active sample.
                return
        if samplestore.get_active_name() == selectedsamplename:
            # we cannot remove the active sample, set another one active.
            samplestore.set_active(prevsample)
        # select the next sample in the list
        self.selectSample(prevsample)
        # remove the selected sample. This will trigger a repopulation of the listWidget.
        samplestore.remove(selectedsamplename)

    def onDuplicateSample(self):
        samplestore = self.credo.services['samplestore']
        assert isinstance(samplestore, SampleStore)
        selectedsamplename = self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
        logger.debug('Selectedsamplename: {}'.format(selectedsamplename))
        sample = samplestore.get_sample(selectedsamplename)
        newsample = Sample(sample)
        m = re.match('(?P<basename>.+)_copy(?P<index>\d*)$', selectedsamplename)
        if m is not None:
            selectedsamplename = m.group('basename')
        logger.debug('Base sample name: {}'.format(selectedsamplename))

        matchingsamples = [re.match('^{}_copy(?P<index>\d+)$'.format(selectedsamplename), sn.title) for sn in
                           samplestore]
        matchingsamples = [int(m.group('index')) for m in matchingsamples if m is not None]
        logger.debug('Copy indices: {}'.format(matchingsamples))
        if not matchingsamples:
            newsample.title = selectedsamplename + '_copy0'
        else:
            maxindex = max(matchingsamples)
            logger.debug('Maxindex: {}'.format(maxindex))
            newsample.title = selectedsamplename + '_copy{}'.format(maxindex + 1)
        logger.debug('Newsample.title: {}'.format(newsample.title))
        if not samplestore.add(newsample):
            logger.error('Cannot add sample {}'.format(newsample.title))
        self.selectSample(newsample.title)

    def onSelectionChanged(self):
        try:
            samplename = self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
        except IndexError:
            return

        def updatespinbox(spinbox, value):
            if spinbox.value() != value:
                spinbox.setValue(value)

        with self._updating_entries:
            sample = self.credo.services['samplestore'].get_sample(samplename)
            assert isinstance(sample, Sample)
            self.sampleNameLineEdit.setText(sample.title)
            if self.descriptionPlainTextEdit.toPlainText() != sample.description:
                self.descriptionPlainTextEdit.setPlainText(sample.description)
            self.categoryComboBox.setCurrentIndex(self.categoryComboBox.findText(sample.category))
            self.situationComboBox.setCurrentIndex(self.situationComboBox.findText(sample.situation))
            self.projectComboBox.setCurrentIndex(self.projectComboBox.findData(sample.project))
            if self.preparedByLineEdit.text() != sample.preparedby:
                self.preparedByLineEdit.setText(sample.preparedby)
            updatespinbox(self.thicknessValDoubleSpinBox, sample.thickness.val)
            updatespinbox(self.thicknessErrDoubleSpinBox, sample.thickness.err)
            updatespinbox(self.xPositionValDoubleSpinBox, sample.positionx.val)
            updatespinbox(self.xPositionErrDoubleSpinBox, sample.positionx.err)
            updatespinbox(self.yPositionValDoubleSpinBox, sample.positiony.val)
            updatespinbox(self.yPositionErrDoubleSpinBox, sample.positiony.err)
            updatespinbox(self.distminusValDoubleSpinBox, sample.distminus.val)
            updatespinbox(self.distminusErrDoubleSpinBox, sample.distminus.err)
            updatespinbox(self.transmissionValDoubleSpinBox, sample.transmission.val)
            updatespinbox(self.transmissionErrDoubleSpinBox, sample.transmission.err)
            self.calendarWidget.setSelectedDate(sample.preparetime.date())
            if sample.maskoverride is None:
                self.maskOverrideCheckBox.setChecked(False)
                self.maskOverrideLineEdit.setText('')
            else:
                self.maskOverrideCheckBox.setChecked(True)
                self.maskOverrideLineEdit.setText(sample.maskoverride)
            self._selectedsample = sample

    def onSampleListChanged(self, samplestore: SampleStore):
        logger.debug('Sample list changed. Selected items: {}'.format(self.listWidget.selectedItems()))
        try:
            previously_selected = self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
        except IndexError:
            previously_selected = samplestore.get_active_name()
        self.listWidget.clear()
        self.listWidget.addItems(sorted([s.title for s in samplestore.get_samples()]))
        logger.debug('Sample list widget contains: {}'.format(
            [self.listWidget.item(i).data(QtCore.Qt.DisplayRole) for i in range(self.listWidget.count())]))
        self.selectSample(previously_selected)

    def cleanup(self):
        for c in self._samplestoreconnections:
            self.credo.services['samplestore'].disconnect(c)
        self._samplestoreconnections = []
        for c in self._accountingconnections:
            self.credo.services['accounting'].disconnect(c)
        self._accountingconnections = []
        super().cleanup()

    def selectSample(self, samplename):
        try:
            self.listWidget.findItems(samplename, QtCore.Qt.MatchExactly)[0].setSelected(True)
        except IndexError:
            self.listWidget.item(0).setSelected(True)
        self.listWidget.setCurrentItem(self.listWidget.selectedItems()[0])
