import datetime
import enum
import logging
from typing import Tuple, List, Final, Dict, Optional, Any

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import pyqtSlot as Slot

from .delegates import SampleEditorDelegate
from .sampleeditor_ui import Ui_Form
from ...utils.filebrowsers import browseMask
from ...utils.window import WindowRequiresDevices
from ....core2.dataclasses.sample import Sample

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ProxyModel(QtCore.QSortFilterProxyModel):
    simplemode: bool = False

    def filterAcceptsColumn(self, source_column: int, source_parent: QtCore.QModelIndex) -> bool:
        return (not self.simplemode) or (source_column == 0)

    def setSimpleMode(self, simplemode: bool):
        self.simplemode = simplemode
        self.invalidateFilter()


class SampleEditor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    _param2widgets: Final[Dict[str, Tuple[str, ...]]] = {
        'title': ('sampleNameLineEdit', 'sampleNameLockToolButton'),
        'description': ('descriptionPlainTextEdit', 'descriptionLockToolButton'),
        'category': ('categoryComboBox', 'categoryLockToolButton'),
        'situation': ('situationComboBox', 'situationLockToolButton'),
        'preparedby': ('preparedByLineEdit', 'preparedByLockToolButton'),
        'thickness': ('thicknessValDoubleSpinBox', 'thicknessErrDoubleSpinBox', 'thicknessLockToolButton'),
        'positionx': ('xPositionValDoubleSpinBox', 'xPositionErrDoubleSpinBox', 'xPositionLockToolButton'),
        'positiony': ('yPositionValDoubleSpinBox', 'yPositionErrDoubleSpinBox', 'yPositionLockToolButton'),
        'distminus': ('distminusValDoubleSpinBox', 'distminusErrDoubleSpinBox', 'distminusLockToolButton'),
        'transmission': ('transmissionValDoubleSpinBox', 'transmissionErrDoubleSpinBox', 'transmissionLockToolButton'),
        'project': ('projectComboBox', 'projectLockToolButton'),
        'maskoverride': ('maskOverrideLineEdit', 'maskOverrideLockToolButton'),
        'preparetime': ('preparationDateDateEdit', 'todayPushButton', 'preparationDateLockToolButton'),
    }
    sampleeditordelegate: SampleEditorDelegate
    proxymodel: ProxyModel

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.proxymodel = ProxyModel()
        self.proxymodel.setSourceModel(self.instrument.samplestore)
        self.treeView.setModel(self.proxymodel)
        self.treeView.setSortingEnabled(True)
        self.treeView.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.treeView.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.treeView.selectionModel().currentRowChanged.connect(self.onCurrentSelectionChanged)
        self.instrument.samplestore.sampleEdited.connect(self.onSampleChangedInStore)
        self.sampleeditordelegate = SampleEditorDelegate(self.treeView)
        self.treeView.setItemDelegate(self.sampleeditordelegate)
        self.situationComboBox.clear()
        self.situationComboBox.addItems([e.value for e in Sample.Situations])
        self.categoryComboBox.clear()
        self.categoryComboBox.addItems([e.value for e in Sample.Categories])
        self.projectComboBox.setModel(self.instrument.projects)
        for attr in self.sampleAttributes():
            for widget in self.widgetsForAttribute(attr):
                if isinstance(widget, QtWidgets.QLineEdit):
                    widget.editingFinished.connect(self.onLineEditEditingFinished)
                elif isinstance(widget, QtWidgets.QComboBox):
                    widget.setCurrentIndex(-1)
                    widget.currentIndexChanged.connect(self.onComboBoxCurrentIndexChanged)
                elif isinstance(widget, QtWidgets.QPlainTextEdit):
                    widget.textChanged.connect(self.onPlainTextEdited)
                elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                    widget.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
                elif isinstance(widget, QtWidgets.QDateEdit):
                    widget.dateChanged.connect(self.onDateEditDateChanged)
                widget.setDisabled(True)
            self.lockToolButton(attr).toggled.connect(self.onLockToolButtonToggled)
            self.lockToolButton(attr).setDisabled(True)
        self.addSamplePushButton.clicked.connect(self.addSample)
        self.removeSamplePushButton.clicked.connect(self.removeSample)
        self.duplicateSamplePushButton.clicked.connect(self.duplicateSample)
        self.maskOverridePushButton.clicked.connect(self.browseMask)
        self.todayPushButton.clicked.connect(self.setToday)
        self.multiColumnPushButton.toggled.connect(self.onMultiColumnToggled)
        self.multiColumnPushButton.setChecked(False)

    @Slot(bool)
    def onMultiColumnToggled(self, checked: bool):
        self.multiColumnPushButton.setText('Detailed' if checked else 'Simple')
        self.proxymodel.setSimpleMode(not checked)
        self.treeView.resize(self.treeView.minimumSizeHint().width(), self.height())
        self.resize(1, self.height())
        for column in range(self.proxymodel.columnCount(QtCore.QModelIndex())):
            self.treeView.resizeColumnToContents(column)

    @Slot()
    def setToday(self):
        self.preparationDateDateEdit.setDate(QtCore.QDate.currentDate())

    @Slot()
    def browseMask(self):
        if (filename := browseMask(self)) is not None:
            self.maskOverrideLineEdit.setText(filename)

    @Slot()
    def addSample(self):
        samplename = self.instrument.samplestore.addSample()
        self.setCurrentSample(samplename)

    @Slot()
    def removeSample(self):
        while lis := self.treeView.selectionModel().selectedRows(0):
            delendum = self.treeView.model().mapToSource(lis[0])
            self.instrument.samplestore.removeRow(delendum.row(), delendum.parent())

    @Slot()
    def duplicateSample(self):
        title = self.currentSampleName()
        if title is None:
            return
        newname = self.instrument.samplestore.addSample(
            self.instrument.samplestore.getFreeSampleName(title),
            self.currentSample()
        )
        self.setCurrentSample(newname)

    def setCurrentSample(self, name: str):
        self.treeView.selectionModel().setCurrentIndex(
            self.treeView.model().mapFromSource(self.instrument.samplestore.indexForSample(name)),
            QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Clear |
            QtCore.QItemSelectionModel.Current | QtCore.QItemSelectionModel.Rows)

    def currentSample(self) -> Optional[Sample]:
        if not self.treeView.selectionModel().currentIndex().isValid():
            return None
        logger.debug(f'Current sample row: {self.treeView.selectionModel().currentIndex().row()}')
        return self.instrument.samplestore[
            self.treeView.model().mapToSource(self.treeView.selectionModel().currentIndex()).row()]

    def currentSampleName(self) -> Optional[str]:
        sam = self.currentSample()
        return None if sam is None else sam.title

    @Slot(bool)
    def onLockToolButtonToggled(self, checked: bool):
        attr = self.attributeForWidget(self.sender())
        self.instrument.samplestore.updateAttributeLocking(self.currentSampleName(), attr, checked)

    @Slot(float)
    def onDoubleSpinBoxValueChanged(self, value: float):
        attribute = self.attributeForWidget(self.sender())
        oldvalue = getattr(self.currentSample(), attribute)
        if len(widgetlist := self.widgetsForAttribute(attribute)) == 2:
            # value and uncertainty. Check which are we
            if widgetlist.index(self.sender()) == 0:
                # we are the value
                self.updateSampleInStore(attribute, (value, oldvalue[1]))
            else:
                assert widgetlist.index(self.sender()) == 1
                self.updateSampleInStore(attribute, (oldvalue[0], value))
        else:
            assert len(self.widgetsForAttribute(attribute)) == 1
            self.updateSampleInStore(attribute, value)

    @Slot(QtCore.QDate)
    def onDateEditDateChanged(self, value: QtCore.QDate):
        attribute = self.attributeForWidget(self.sender())
        date = self.sender().date()
        self.updateSampleInStore(attribute, datetime.date(date.year(), date.month(), date.day()))

    @Slot(int)
    def onComboBoxCurrentIndexChanged(self, currentIndex: int):
        logger.debug(
            f'onComboBoxCurrentIndexChanged. Current text: {self.sender().currentText()}. Sender: {self.sender().objectName()}')
        attribute = self.attributeForWidget(self.sender())
        if self.sender() is self.situationComboBox:
            self.updateSampleInStore(attribute, Sample.Situations(self.sender().currentText()))
        elif self.sender() is self.categoryComboBox:
            self.updateSampleInStore(attribute, Sample.Categories(self.sender().currentText()))
        elif self.sender() is self.projectComboBox:
            self.updateSampleInStore(attribute, self.sender().currentText())
        else:
            assert False

    @Slot()
    def onPlainTextEdited(self):
        attribute = self.attributeForWidget(self.sender())
        self.updateSampleInStore(attribute, self.sender().toPlainText())

    @Slot()
    def onLineEditEditingFinished(self):
        attribute = self.attributeForWidget(self.sender())
        self.updateSampleInStore(attribute, self.sender().text())

    def updateSampleInStore(self, attribute: str, newvalue: Any):
        try:
            self.instrument.samplestore.updateSample(self.currentSampleName(), attribute, newvalue)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Error while updating the sample: {exc}')

    @Slot(str, str, object)
    def onSampleChangedInStore(self, samplename: str, attribute: str, newvalue: Any):
        logger.debug(
            f'Sample {samplename=} changed in the store: {attribute=} is now {newvalue=}. Current sample name: {self.currentSampleName()}')
        if samplename != self.currentSampleName():
            return
        for i, widget in enumerate(self.widgetsForAttribute(attribute)):
            widget.blockSignals(True)
            try:
                if isinstance(widget, QtWidgets.QPlainTextEdit) and (newvalue != widget.toPlainText()):
                    widget.setPlainText(newvalue)
                elif isinstance(widget, QtWidgets.QLineEdit) and (newvalue != widget.text()):
                    widget.setText(newvalue)
                elif isinstance(widget, QtWidgets.QComboBox):
                    logger.debug(f'Newvalue: {newvalue}. {type(newvalue)=}')
                    if isinstance(newvalue, str) and (widget.currentText() != newvalue):
                        widget.setCurrentIndex(widget.findText(newvalue))
                    elif (newvalue is None) and (widget.currentIndex() >= 0):
                        widget.setCurrentIndex(-1)
                    elif (newvalue is None) and (widget.currentIndex() < 0):
                        pass
                    elif isinstance(newvalue, enum.Enum) and (widget.currentText() != newvalue.value):
                        widget.setCurrentIndex(widget.findText(newvalue.value))
                    else:
                        # must not fail: we can reach this line if no change is needed in the widget value
                        pass
                elif isinstance(widget, QtWidgets.QDoubleSpinBox) and isinstance(newvalue, tuple) and (
                        len(newvalue) == 2) and (widget.value() != newvalue[i]):
                    widget.setValue(newvalue[i])
                else:
                    # must not fail: we can reach this line if no change is needed in the widget value
                    pass
            finally:
                widget.blockSignals(False)
            self.updateLockButtonState(self.instrument.samplestore[samplename], attribute)

    @Slot(QtCore.QItemSelection, QtCore.QItemSelection)
    def onSelectionChanged(self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection):
        nonemptyselection = len(self.treeView.selectionModel().selectedRows())
        self.removeSamplePushButton.setEnabled(nonemptyselection)

    def updateEditWidgets(self, sample: Optional[Sample]):
        for attribute in self.sampleAttributes():
            value = getattr(sample, attribute) if sample is not None else None
            logger.debug(f'attribute {attribute}: {value}')
            for i, widget in enumerate(self.widgetsForAttribute(attribute)):
                widget.setEnabled((sample is not None) and (not sample.isLocked(attribute)))
                widget.blockSignals(True)
                try:
                    if isinstance(widget, QtWidgets.QLineEdit):
                        widget.setText(value if value is not None else '')
                    elif isinstance(widget, QtWidgets.QPlainTextEdit):
                        widget.setPlainText(value if value is not None else '')
                    elif isinstance(widget, QtWidgets.QComboBox):
                        if value is None:
                            widget.setCurrentIndex(-1)
                            continue
                        elif not isinstance(value, str):
                            # should be an Enum element
                            value = value.value
                        widget.setCurrentIndex(widget.findText(value))
                    elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                        if isinstance(value, tuple):
                            widget.setValue(value[i])
                        else:
                            widget.setValue(value if value is not None else 0.0)
                    elif isinstance(widget, QtWidgets.QDateEdit):
                        if value is None:
                            widget.setDate(QtCore.QDate.currentDate())
                        else:
                            assert isinstance(value, datetime.date)
                            widget.setDate(QtCore.QDate(value.year, value.month, value.day))
                    else:
                        assert False
                finally:
                    widget.blockSignals(False)
            self.updateLockButtonState(sample, attribute)

    def updateLockButtonState(self, sample: Optional[Sample], attribute: str):
        ltb = self.lockToolButton(attribute)
        ltb.setEnabled(sample is not None)
        ltb.blockSignals(True)
        try:
            ltb.setChecked(sample.isLocked(attribute) if sample is not None else False)
            ltb.setIcon(
                QtGui.QIcon.fromTheme(
                    'lock' if ((sample is not None) and sample.isLocked(attribute)) else 'unlock'))
        finally:
            ltb.blockSignals(False)

    @Slot(QtCore.QModelIndex, QtCore.QModelIndex)
    def onCurrentSelectionChanged(self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex):
        self.updateEditWidgets(self.currentSample())

    def widgetsForAttribute(self, attribute: str) -> Tuple[QtWidgets.QWidget, ...]:
        return tuple([getattr(self, wn) for wn in self._param2widgets[attribute][:-1]])

    def sampleAttributes(self) -> List[str]:
        return list(self._param2widgets.keys())

    def lockToolButton(self, attribute: str) -> QtWidgets.QToolButton:
        return getattr(self, self._param2widgets[attribute][-1])

    def attributeForWidget(self, widget: QtWidgets.QWidget) -> str:
        return [attr for attr, wnames in self._param2widgets.items() if widget.objectName() in wnames][0]
