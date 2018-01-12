from typing import List, Any

from PyQt5 import QtCore, QtWidgets


class BackgroundSubtractionModel(QtCore.QAbstractItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._samplenamelist = []
        self._samples = []

    def sampleNameList(self):
        return self._samplenamelist[:]

    def setSampleNameList(self, samplenames:List[str]):
        self._samplenamelist = list(samplenames)

    def addSample(self, samplename):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._samples), len(self._samples))
        self._samples.append([samplename, None])
        self.endInsertRows()

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...):
        self.beginRemoveRows(QtCore.QModelIndex(),row, row)
        del self._samples[row]
        self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self._samples=[]
        self.endResetModel()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role in [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]:
            if self._samples[index.row()][index.column()] is None:
                if role == QtCore.Qt.DisplayRole:
                    return 'Select sample...'
                else:
                    return ''
            return self._samples[index.row()][index.column()]
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role==QtCore.Qt.DisplayRole:
            return ['Sample name', 'Background name'][section]
        return None

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._samples)

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 2

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...):
        if role==QtCore.Qt.EditRole:
            self._samples[index.row()][index.column()]=value
            return True
        return False

    def getBackgroundSubtractionList(self):
        return [(s[0], s[1], None) for s in self._samples if s[0] is not None and s[1] is not None]

class ComboBoxDelegate(QtWidgets.QStyledItemDelegate):
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        editor = QtWidgets.QComboBox(parent)
        editor.addItems(index.model().sampleNameList())
        return editor

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex):
        name = index.data(QtCore.Qt.EditRole)
        assert isinstance(editor, QtWidgets.QComboBox)
        editor.setCurrentIndex(editor.findText(name))

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        editor.setGeometry(option.rect)

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel, index: QtCore.QModelIndex):
        model.setData(index, editor.currentText(), QtCore.Qt.EditRole)
