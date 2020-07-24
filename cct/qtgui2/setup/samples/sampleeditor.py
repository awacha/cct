import datetime
import logging
from typing import Tuple, Dict, Optional, Any

from PyQt5 import QtWidgets, QtCore, QtGui

from .delegates import SampleEditorDelegate
from .sampleeditor_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.samples.sample import Sample, LockState

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SampleEditor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    _sampleeditordelegate: SampleEditorDelegate
    _sampleproperty2widgets: Dict[str, Tuple[str, ...]] = {
        'title': ('sampleNameLineEdit', 'sampleNameLockToolButton'),
        'description': ('descriptionPlainTextEdit', 'descriptionLockToolButton'),
        'category': ('categoryComboBox', 'categoryLockToolButton'),
        'situation': ('situationComboBox', 'situationLockToolButton'),
        'preparedby': ('preparedByLineEdit', 'preparedByLockToolButton'),
        'preparetime': ('preparationDateDateEdit', 'preparationDateLockToolButton'),
        'thickness': ('thicknessValDoubleSpinBox', 'thicknessErrDoubleSpinBox', 'thicknessLockToolButton'),
        'positionx': ('xPositionValDoubleSpinBox', 'yPositionValDoubleSpinBox', 'xPositionLockToolButton'),
        'positiony': ('yPositionValDoubleSpinBox', 'yPositionValDoubleSpinBox', 'yPositionLockToolButton'),
        'distminus': ('distminusValDoubleSpinBox', 'distminusErrDoubleSpinBox', 'distminusLockToolButton'),
        'transmission': ('transmissionValDoubleSpinBox', 'transmissionErrDoubleSpinBox', 'transmissionLockToolButton'),
        'project': ('projectComboBox', 'projectLockToolButton'),
        'maskoverride': ('maskOverrideLineEdit', 'maskOverrideLockToolButton'),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.samplestore)
        self.instrument.samplestore.setSingleColumnMode(False)
        self.instrument.samplestore.modelReset.connect(self.resizeTreeViewColumns)
        self.instrument.samplestore.dataChanged.connect(self.resizeTreeViewColumns)
        self.instrument.samplestore.rowsInserted.connect(self.resizeTreeViewColumns)
        self.instrument.samplestore.rowsRemoved.connect(self.resizeTreeViewColumns)
        self.treeView.selectionModel().currentChanged.connect(self.currentSampleSelected)
        self.situationComboBox.addItems([x.value for x in list(Sample.Situations)])
        self.categoryComboBox.addItems([x.value for x in list(Sample.Categories)])
        self.frame.setEnabled(False)
        for propname, widgets in self._sampleproperty2widgets.items():
            widgets = [getattr(self, w) for w in widgets]
            lockbutton = widgets[-1]
            assert isinstance(lockbutton, QtWidgets.QToolButton)
            lockbutton.toggled.connect(self.onLockButtonToggled)
            lockbutton.setIcon(QtGui.QIcon.fromTheme('unlock'))
            if (len(widgets) == 2) and isinstance(widgets[0], QtWidgets.QLineEdit):
                widgets[0].editingFinished.connect(self.onLineEditEditingFinished)
            elif (len(widgets) == 2) and isinstance(widgets[0], QtWidgets.QPlainTextEdit):
                widgets[0].textChanged.connect(self.onPlainTextEditTextChanged)
            elif (len(widgets) == 2) and isinstance(widgets[0], QtWidgets.QComboBox):
                widgets[0].currentIndexChanged.connect(self.onComboBoxCurrentIndexChanged)
            elif (len(widgets) == 2) and isinstance(widgets[0], QtWidgets.QDateEdit):
                widgets[0].dateChanged.connect(self.onDateEditDateChanged)
            elif ((len(widgets) == 3)
                  and isinstance(widgets[0], QtWidgets.QDoubleSpinBox)
                  and isinstance(widgets[1], QtWidgets.QDoubleSpinBox)):
                widgets[0].valueChanged.connect(self.onDoubleSpinBoxValueChanged)
                widgets[1].valueChanged.connect(self.onDoubleSpinBoxValueChanged)
            else:
                assert False
        self.maskOverridePushButton.clicked.connect(self.browseMask)
        self.todayPushButton.clicked.connect(self.setToday)
        self.resizeTreeViewColumns()
        self._sampleeditordelegate = SampleEditorDelegate(self.treeView)
        self.treeView.setItemDelegate(self._sampleeditordelegate)
        self.addSamplePushButton.clicked.connect(self.addSample)
        self.removeSamplePushButton.clicked.connect(self.removeSample)
        self.duplicateSamplePushButton.clicked.connect(self.duplicateSample)
        self.removeSamplePushButton.setEnabled(False)
        self.duplicateSamplePushButton.setEnabled(False)

    def addSample(self):
        samplename = self.instrument.samplestore.addSample('Untitled')
        self.treeView.selectionModel().setCurrentIndex(
            self.instrument.samplestore.findSample(samplename),
            QtCore.QItemSelectionModel.Rows | QtCore.QItemSelectionModel.Clear |
            QtCore.QItemSelectionModel.SelectCurrent
        )

    def removeSample(self):
        sample = self.currentSample()
        if not sample:
            return
        self.instrument.samplestore.removeSample(sample.title)

    def duplicateSample(self):
        sample = self.currentSample()
        if not sample:
            return
        newtitle = self.instrument.samplestore.duplicateSample(sample.title)
        self.treeView.selectionModel().setCurrentIndex(
            self.instrument.samplestore.findSample(newtitle),
            QtCore.QItemSelectionModel.Rows | QtCore.QItemSelectionModel.Clear |
            QtCore.QItemSelectionModel.SelectCurrent
        )

    def setToday(self):
        self.preparationDateDateEdit.setDate(QtCore.QDate.currentDate())

    def browseMask(self):
        maskfile, filter_ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Select mask file', '', 'Mask files (*.mat; *.npy);;All files (*)', 'Mask files (*.mat; *.npy)')
        if not maskfile:
            return
        self.maskOverrideLineEdit.setText(maskfile)

    def changeSample(self, attribute: str, newvalue: Any):
        logger.debug(f'changeSample: {attribute}, {newvalue}')
        focusedwidget = self.focusWidget()
        sample = self.currentSample()
        title = sample.title
        if sample is None:
            return
        if getattr(sample, attribute) != newvalue:
            logger.debug(f'Really changeSample: {attribute}, {newvalue}')
            setattr(sample, attribute, newvalue)
            self.instrument.samplestore.updateSample(title, sample)
            self.treeView.selectionModel().setCurrentIndex(
                self.instrument.samplestore.findSample(sample.title),
                QtCore.QItemSelectionModel.SelectCurrent |
                QtCore.QItemSelectionModel.Clear |
                QtCore.QItemSelectionModel.Rows)
            focusedwidget.setFocus()

    def attributeForWidget(self, widget: Optional[QtWidgets.QWidget] = None):
        if widget is None:
            widget = self.sender()
        assert isinstance(widget, QtWidgets.QWidget)
        return [p for p, ws in self._sampleproperty2widgets.items() if widget.objectName() in ws][0]

    def currentSample(self) -> Optional[Sample]:
        if self.treeView.currentIndex().isValid():
            return self.instrument.samplestore[self.treeView.currentIndex().row()]
        else:
            return None

    def onDoubleSpinBoxValueChanged(self, value: float):
        attr = self.attributeForWidget()
        prevvalue = getattr(self.currentSample(), attr)
        if self.sender().objectName().endswith('ErrDoubleSpinBox'):
            self.changeSample(attr, (prevvalue[0], value))
        elif self.sender().objectName().endswith('ValDoubleSpinBox'):
            self.changeSample(attr, (value, prevvalue[1]))
        else:
            self.changeSample(self.attributeForWidget(), value)

    def onDateEditDateChanged(self, date: QtCore.QDate):
        self.changeSample(self.attributeForWidget(), datetime.date(date.year(), date.month(), date.day()))

    def onPlainTextEditTextChanged(self):
        self.changeSample(self.attributeForWidget(), self.sender().toPlainText())

    def onComboBoxCurrentIndexChanged(self):
        self.changeSample(self.attributeForWidget(), self.sender().currentText())

    def onLineEditEditingFinished(self):
        attr = self.attributeForWidget()
        text = self.sender().text()
        if (attr == 'title') and (text in self.instrument.samplestore):
            # avoid making duplicate titles or rename this sample to the same name.
            logger.debug('Not setting duplicate title.')
            if self.currentSample().title != text:
                # re-set the title editor
                QtWidgets.QMessageBox.warning(self, 'Duplicate title',
                                              f'Another sample with title {text} already exists.')
                self.sender().setText(self.currentSample().title)
        else:
            self.changeSample(attr, text)

    def onLockButtonToggled(self, state: bool):
        focusedwidget = self.focusWidget()
        lockbutton = self.sender()
        assert isinstance(lockbutton, QtWidgets.QToolButton)
        lockbutton.setIcon(QtGui.QIcon.fromTheme('lock' if state else 'unlock'))
        attrname = [a for a, ws in self._sampleproperty2widgets.items() if lockbutton.objectName() in ws][0]
        currentsample = self.currentSample()
        setattr(currentsample, attrname, LockState.LOCKED if state else LockState.UNLOCKED)
        self.removeSamplePushButton.setEnabled(not currentsample.isLocked('title'))
        self.instrument.samplestore.updateSample(currentsample.title, currentsample)
        self.treeView.selectionModel().setCurrentIndex(
            self.instrument.samplestore.findSample(currentsample.title),
            QtCore.QItemSelectionModel.SelectCurrent |
            QtCore.QItemSelectionModel.Clear |
            QtCore.QItemSelectionModel.Rows)
        focusedwidget.setFocus()

    def resizeTreeViewColumns(self):
        for c in range(self.instrument.samplestore.columnCount()):
            self.treeView.resizeColumnToContents(c)

    def currentSampleSelected(self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex):
        logger.debug('currentSampleSelected')
        if not current.isValid():
            self.removeSamplePushButton.setEnabled(False)
            self.duplicateSamplePushButton.setEnabled(False)
            self.frame.setEnabled(False)
            return
        self.duplicateSamplePushButton.setEnabled(True)
        self.frame.setEnabled(True)
        sample = self.instrument.samplestore[current.row()]
        self.removeSamplePushButton.setEnabled(not sample.isLocked('title'))
        for attribute, widgetnames in self._sampleproperty2widgets.items():
            widgets = [getattr(self, wn) for wn in widgetnames]
            for w in widgets:
                w.blockSignals(True)
            try:
                if (len(widgets) == 2) and isinstance(widgets[0], QtWidgets.QLineEdit):
                    widgets[0].setText(getattr(sample, attribute))
                elif (len(widgets) == 2) and isinstance(widgets[0], QtWidgets.QPlainTextEdit):
                    widgets[0].setPlainText(getattr(sample, attribute))
                elif (len(widgets) == 2) and isinstance(widgets[0], QtWidgets.QComboBox):
                    value = getattr(sample, attribute)
                    if value is None:
                        widgets[0].setCurrentIndex(-1)
                        continue
                    elif not isinstance(value, str):
                        value = value.value
                    widgets[0].setCurrentIndex(widgets[0].findText(value))
                elif (len(widgets) == 2) and isinstance(widgets[0], QtWidgets.QDateEdit):
                    date = getattr(sample, attribute)
                    widgets[0].setDate(QtCore.QDate(date.year, date.month, date.day))
                elif ((len(widgets) == 3)
                      and isinstance(widgets[0], QtWidgets.QDoubleSpinBox)
                      and isinstance(widgets[1], QtWidgets.QDoubleSpinBox)):
                    for w in widgets[:-1]:
                        if 'ErrDoubleSpinBox' in w.objectName():
                            w.setValue(getattr(sample, attribute)[1])
                        elif 'ValDoubleSpinBox' in w.objectName():
                            w.setValue(getattr(sample, attribute)[0])
                        else:
                            assert False
                else:
                    assert False
                widgets[-1].setChecked(sample.isLocked(attribute))
                widgets[-1].setIcon(QtGui.QIcon.fromTheme('lock' if sample.isLocked(attribute) else 'unlock'))
            finally:
                for w in widgets:
                    w.blockSignals(False)
        logger.debug('End of currentSampleSelected')
