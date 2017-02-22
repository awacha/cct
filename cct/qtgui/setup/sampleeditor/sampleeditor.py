import logging
import re

from PyQt5 import QtWidgets, QtCore, QtGui

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from .sampleeditor_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.services.samples import Sample, SampleStore


class SampleEditor(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo=kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo)
        self.setupUi(self)
        self._samplestoreconnections=[]

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.onSampleListChanged(self.credo.services['samplestore'])
        self.listWidget.itemSelectionChanged.connect(self.onSelectionChanged)
        self.sampleNameLineEdit.setValidator(QtGui.QRegularExpressionValidator(QtCore.QRegularExpression('[-A-Za-z0-9_]+')))
        self.addSamplePushButton.clicked.connect(self.onAddSample)
        self.removeSamplePushButton.clicked.connect(self.onRemoveSample)
        self.duplicateSamplePushButton.clicked.connect(self.onDuplicateSample)

    def onAddSample(self):
        samplestore = self.credo.services['samplestore']
        assert isinstance(samplestore, SampleStore)
        sampletitle = 'Unnamed'
        index = 0
        while not samplestore.add(Sample(sampletitle)):
            index +=1
            sampletitle = 'Unnamed_{:d}'.format(index)
        samplestore.set_active(sampletitle)

    def onRemoveSample(self):
        selectedsamplename = self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
        samplestore = self.credo.services['samplestore']
        assert isinstance(samplestore, SampleStore)
        samplenames=list(samplestore)
        try:
            # we will activate the next sample in the list
            nextsample = samplenames[samplenames.index(selectedsamplename)+1]
        except IndexError:
            # this happens when we are trying to remove the last sample in the list
            try:
                nextsample = samplenames[-2]
            except IndexError:
                # this happens when there is only one sample left in the samplestore and we want
                # to delete that. This is not possible, since there should always be an active sample.
                return
        if samplestore.get_active_name()==selectedsamplename:
            # we cannot remove the active sample, set another one active.
            samplestore.set_active(nextsample)
        # select the next sample in the list
        self.listWidget.findItems(nextsample, QtCore.Qt.MatchExactly)[0].setSelected(True)
        # remove the selected sample. This will trigger a repopulation of the listWidget.
        samplestore.remove(selectedsamplename)


    def onDuplicateSample(self):
        samplestore = self.credo.services['samplestore']
        assert isinstance(samplestore, SampleStore)
        selectedsamplename = self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
        sample = samplestore.get_sample(selectedsamplename)
        newsample = Sample(sample)
        m=re.match('(?P<basename>.+)_copy(?P<index>\d*)$', selectedsamplename)
        if m is not None:
            selectedsamplename = m.group('basename')

        matchingsamples = [re.match('^{}_copy(?P<index>\d+)$'.format(selectedsamplename), sn.title) for sn in samplestore]
        matchingsamples = [int(m.group('index')) for m in matchingsamples if m is not None]
        if not matchingsamples:
            newsample.title = selectedsamplename+'_copy0'
        else:
            maxindex = max(matchingsamples)
            newsample.title == selectedsamplename+'_copy{}'.format(maxindex+1)
        assert samplestore.add(newsample)
        self.listWidget.findItems(newsample.title, QtCore.Qt.MatchExactly)[0].setSelected(True)

    def onSelectionChanged(self):
        samplename=self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
        sample = self.credo.services['samplestore'].get_sample(samplename)
        assert isinstance(sample, Sample)
        self.sampleNameLineEdit.setText(sample.title)
        self.descriptionPlainTextEdit.setPlainText(sample.description)
        self.categoryComboBox.setCurrentIndex(self.categoryComboBox.findText(sample.category))
        self.situationComboBox.setCurrentIndex(self.situationComboBox.findText(sample.situation))
        self.preparedByLineEdit.setText(sample.preparedby)
        self.thicknessValDoubleSpinBox.setValue(sample.thickness.val)
        self.thicknessErrDoubleSpinBox.setValue(sample.thickness.err)
        self.xPositionValDoubleSpinBox.setValue(sample.positionx.val)
        self.xPositionErrDoubleSpinBox.setValue(sample.positionx.err)
        self.yPositionValDoubleSpinBox.setValue(sample.positiony.val)
        self.yPositionErrDoubleSpinBox.setValue(sample.positiony.err)
        self.distminusValDoubleSpinBox.setValue(sample.distminus.val)
        self.distminusErrDoubleSpinBox.setValue(sample.distminus.err)
        self.transmissionValDoubleSpinBox.setValue(sample.transmission.val)
        self.transmissionErrDoubleSpinBox.setValue(sample.transmission.err)
        self.calendarWidget.setSelectedDate(sample.preparetime.date())

    def onSampleListChanged(self, samplestore:SampleStore):
        logger.debug('Selected items: {}'.format(self.listWidget.selectedItems()))
        try:
            previously_selected=self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
        except IndexError:
            previously_selected=samplestore.get_active_name()
        self.listWidget.clear()
        self.listWidget.addItems(sorted([s.title for s in samplestore.get_samples()]))
        try:
            self.listWidget.findItems(previously_selected, QtCore.Qt.MatchExactly)[0].setSelected(True)
        except IndexError:
            self.listWidget.item(0).setSelected(True)
        self.listWidget.setCurrentItem(self.listWidget.selectedItems()[0])


