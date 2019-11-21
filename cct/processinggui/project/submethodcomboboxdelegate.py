from PyQt5 import QtCore, QtWidgets

from ..models.subtraction import Subtraction


class SubtractionMethodComboBoxDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        sub = index.model()[index]
        assert isinstance(sub, Subtraction)
        editor = QtWidgets.QComboBox(parent)
        editor.addItems(sub.ValidMethods)
        editor.setCurrentIndex(0)
        editor.setFrame(False)
        return editor

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex) -> None:
        editor.setCurrentIndex(editor.findText(index.data(QtCore.Qt.EditRole)))
        if editor.currentIndex() < 0:
            editor.setCurrentIndex(0)

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        assert isinstance(editor, QtWidgets.QComboBox)
        model.setData(index, editor.currentText() if editor.currentIndex()>0 else editor.itemText(0), QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex) -> None:
        editor.setGeometry(option.rect)

