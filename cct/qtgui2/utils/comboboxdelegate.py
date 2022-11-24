from PyQt5 import QtWidgets, QtCore
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ComboBoxDelegate(QtWidgets.QStyledItemDelegate):
    """A treeview edit delegate for presenting choices in a combo box

    The current value is taken from the EditRole. The list of choices is in UserRole.
    """
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        w = QtWidgets.QComboBox(parent)
        w.addItems(index.data(QtCore.Qt.ItemDataRole.UserRole))
        w.setFrame(False)
        return w

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex) -> None:
        editor.setGeometry(option.rect)

    def setEditorData(self, editor: QtWidgets.QComboBox, index: QtCore.QModelIndex) -> None:
        assert isinstance(editor, QtWidgets.QComboBox)
        editor.setCurrentIndex(editor.findText(index.data(QtCore.Qt.ItemDataRole.EditRole)))

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        model.setData(index, editor.currentText(), QtCore.Qt.ItemDataRole.EditRole)
