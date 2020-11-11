import logging

from PyQt5 import QtWidgets, QtCore

from ....core2.instrument.components.samples.samplestore import SampleStore, Sample
from ....core2.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SampleEditorDelegate(QtWidgets.QStyledItemDelegate):
    def _get_attribute(self, index: QtCore.QModelIndex) -> str:
        logger.debug(f'_get_attribute({index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=}')
        model = Instrument.instance().samplestore
        assert isinstance(model, SampleStore)
        return model._columns[index.column()][0]

    def createEditor(self, parent: QtWidgets.QWidget, option: 'QStyleOptionViewItem',
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        logger.debug(f'createEditor({index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=}')
        if self._get_attribute(index) in ['title', 'description', 'preparedby', 'maskoverride']:
            w = super().createEditor(parent, option, index)
        elif self._get_attribute(index) in ['positionx', 'positiony', 'distminus']:
            w = QtWidgets.QDoubleSpinBox(parent)
            w.setRange(-1000, 1000)
            w.setDecimals(4)
            w.setSingleStep(0.1)
        elif self._get_attribute(index) == 'preparetime':
            w = QtWidgets.QDateEdit(parent)
            w.setCalendarPopup(True)
        elif self._get_attribute(index) == 'transmission':
            w = QtWidgets.QDoubleSpinBox(parent)
            w.setRange(0, 1)
            w.setSingleStep(0.01)
            w.setDecimals(4)
        elif self._get_attribute(index) == 'thickness':
            w = QtWidgets.QDoubleSpinBox(parent)
            w.setRange(0, 1000)
            w.setSingleStep(0.01)
            w.setDecimals(4)
        elif self._get_attribute(index) == 'category':
            w = QtWidgets.QComboBox(parent)
            w.addItems([x.value for x in Sample.Categories])
        elif self._get_attribute(index) == 'situation':
            w = QtWidgets.QComboBox(parent)
            w.addItems([x.value for x in Sample.Situations])
        else:
            w = super().createEditor(parent, option, index)
        w.setFrame(False)
        return w

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: 'QStyleOptionViewItem',
                             index: QtCore.QModelIndex) -> None:
        logger.debug(f'updateEditorGeometry({index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=}')
        editor.setGeometry(option.rect)

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex) -> None:
        logger.debug(f'setEditorData({index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=}')
        attribute = self._get_attribute(index)
        sample = Instrument.instance().samplestore[index.row()]
        assert isinstance(sample, Sample)
        if attribute in ['title', 'description', 'preparedby', 'maskoverride', 'preparetime']:
            super().setEditorData(editor, index)
        elif attribute in ['positionx', 'positiony', 'thickness', 'transmission', 'distminus']:
            assert isinstance(editor, QtWidgets.QDoubleSpinBox)
            editor.setValue(getattr(sample, attribute)[0])
        elif attribute in ['category', 'situation']:
            assert isinstance(editor, QtWidgets.QComboBox)
            editor.setCurrentIndex(editor.findText(getattr(sample, attribute).value))
        elif attribute == 'preparetime':
            assert isinstance(editor, QtWidgets.QDateEdit)
            editor.setDate(QtCore.QDate(sample.preparetime.year, sample.preparetime.month, sample.preparetime.day))
        else:
            return super().setEditorData(editor, index)

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        logger.debug(f'setModelData({index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=}')
        if isinstance(editor, QtWidgets.QDoubleSpinBox):
            model.setData(index, editor.value(), QtCore.Qt.EditRole)
        elif isinstance(editor, QtWidgets.QComboBox):
            model.setData(index, editor.currentText(), QtCore.Qt.EditRole)
        else:
            super().setModelData(editor, model, index)
