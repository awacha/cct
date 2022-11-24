import logging

from PyQt5 import QtWidgets, QtCore

from ...core2.processing.tasks.subtraction import SubtractionData, SubtractionScalingMode
from ...core2.processing.processing import Processing
from ..utils.qrangeentry import QRangeEntry
from ..utils.valueanduncertaintyentry import ValueAndUncertaintyEntry

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SubtractionDelegate(QtWidgets.QStyledItemDelegate):
    project: Processing

    def __init__(self, parent, project: Processing):
        self.project = project
        super().__init__(parent)

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        logger.debug(f'createEditor({index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=}')
        if (index.column() == 0) or (index.column() == 1):
            # sample name or background name
            w = QtWidgets.QComboBox(parent)
            w.addItems(['-- None --'] + sorted(self.project.settings.h5io.samplenames()))
        elif index.column() == 2:
            w = QtWidgets.QComboBox(parent)
            w.addItems(sorted([mode.value for mode in SubtractionScalingMode]))
        elif (index.column() == 3):
            scalingmode = index.model().index(index.row(), 2, index.parent()).data(QtCore.Qt.ItemDataRole.EditRole)
            assert isinstance(scalingmode, SubtractionScalingMode)
            if scalingmode in [SubtractionScalingMode.PowerLaw, SubtractionScalingMode.Interval]:
                w = QRangeEntry(parent=parent)
                w.setDecimals(4)
                w.setRange(0, 99)
            elif scalingmode in [SubtractionScalingMode.Constant]:
                w = ValueAndUncertaintyEntry(parent=parent)
                w.setDecimals(8)
                w.setRange(0, 1e8)
            else:
                return None
        else:
            assert False
        w.setFrame(False)
        w.setAutoFillBackground(True)
        return w

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: 'QStyleOptionViewItem',
                             index: QtCore.QModelIndex) -> None:
        logger.debug(f'updateEditorGeometry({index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=}')
        editor.setGeometry(option.rect)

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex) -> None:
        logger.debug(f'setEditorData({index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=}')
        if (index.column() == 0) or (index.column() == 1):
            assert isinstance(editor, QtWidgets.QComboBox)
            if index.data(QtCore.Qt.ItemDataRole.EditRole) is None:
                editor.setCurrentIndex(0)
            else:
                editor.setCurrentIndex(editor.findText(index.data(QtCore.Qt.ItemDataRole.EditRole)))
        elif index.column() == 2:
            assert isinstance(editor, QtWidgets.QComboBox)
            mode = index.data(QtCore.Qt.ItemDataRole.EditRole)
            assert isinstance(mode, SubtractionScalingMode)
            editor.setCurrentIndex(editor.findText(mode.value))
        else:
            assert index.column() == 3
            scalingmode = index.model().index(index.row(), 2, index.parent()).data(QtCore.Qt.ItemDataRole.EditRole)
            assert isinstance(scalingmode, SubtractionScalingMode)
            if scalingmode in [SubtractionScalingMode.PowerLaw, SubtractionScalingMode.Interval]:
                assert isinstance(editor, QRangeEntry)
                qmin, qmax, qcount = index.data(QtCore.Qt.ItemDataRole.EditRole)
                editor.setValue(qmin, qmax, qcount)
            elif scalingmode in [SubtractionScalingMode.Constant]:
                assert isinstance(editor, ValueAndUncertaintyEntry)
                val, unc = index.data(QtCore.Qt.ItemDataRole.EditRole)
                editor.setValue(val, unc)
            else:
                assert False

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        logger.debug(f'setModelData({index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=}')
        if (index.column() == 0) or (index.column() == 1):
            assert isinstance(editor, QtWidgets.QComboBox)
            if editor.currentIndex() == 0:
                model.setData(index, None, QtCore.Qt.ItemDataRole.EditRole)
            else:
                model.setData(index, editor.currentText(), QtCore.Qt.ItemDataRole.EditRole)
        elif index.column() == 2:
            assert isinstance(editor, QtWidgets.QComboBox)
            model.setData(index, SubtractionScalingMode(editor.currentText()), QtCore.Qt.ItemDataRole.EditRole)
        else:
            assert index.column() == 3
            scalingmode = index.model().index(index.row(), 2, index.parent()).data(QtCore.Qt.ItemDataRole.EditRole)
            assert isinstance(scalingmode, SubtractionScalingMode)
            if scalingmode in [SubtractionScalingMode.PowerLaw, SubtractionScalingMode.Interval]:
                assert isinstance(editor, QRangeEntry)
                model.setData(index, editor.value(), QtCore.Qt.ItemDataRole.EditRole)
            elif scalingmode in [SubtractionScalingMode.Constant]:
                assert isinstance(editor, ValueAndUncertaintyEntry)
                model.setData(index, editor.value(), QtCore.Qt.ItemDataRole.EditRole)
            else:
                assert False
