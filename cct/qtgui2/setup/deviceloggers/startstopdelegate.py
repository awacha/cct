from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Slot
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class StartStopDelegate(QtWidgets.QStyledItemDelegate):
    """A treeview edit delegate for a start/stop button

    The current value is taken from the EditRole
    """
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        w = QtWidgets.QPushButton(parent)
        w.setCheckable(True)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(':/icons/stop.svg'), state=QtGui.QIcon.State.On)
        icon.addPixmap(QtGui.QPixmap(':/icons/start.svg'), state=QtGui.QIcon.State.Off)
        w.setIcon(icon)
        w.toggled.connect(self.onToggled)
        #w.setFrame(False)
        return w

    def updateEditorGeometry(self, editor: QtWidgets.QPushButton, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex) -> None:
        editor.setGeometry(option.rect)

    def setEditorData(self, editor: QtWidgets.QPushButton, index: QtCore.QModelIndex) -> None:
        assert isinstance(editor, QtWidgets.QPushButton)
        if index.data(QtCore.Qt.ItemDataRole.EditRole):
            editor.setText('Stop')
            editor.blockSignals(True)
            editor.setChecked(True)
            editor.blockSignals(False)
        else:
            editor.setText('Start')
            editor.blockSignals(True)
            editor.setChecked(False)
            editor.blockSignals(False)

    def setModelData(self, editor: QtWidgets.QPushButton, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        model.setData(index, editor.isChecked(), QtCore.Qt.ItemDataRole.EditRole)

    @Slot()
    def onToggled(self):
        self.commitData.emit(self.sender())
        self.closeEditor.emit(self.sender(), self.SubmitModelCache)

