from typing import List, Any

from PyQt5 import QtCore, QtWidgets, QtGui
import time

class BackgroundSubtractionModel(QtCore.QAbstractItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._samplenamelist = []
        self._samples = [] # list of [samplename, backgroundname, background_scaling, enabled for processing]

    def sampleNameList(self):
        return self._samplenamelist[:]

    def setSampleNameList(self, samplenames:List[str]):
        self._samplenamelist = list(samplenames)
        for sn in self._samplenamelist:
            if sn not in [s[0] for s in self._samples]:
                self.addSample(sn)
        self.beginResetModel()
        self._samples = [s for s in self._samples if s[0] in self._samplenamelist]
        for i in range(len(self._samples)):
            if self._samples[i][1] not in self._samplenamelist:
                self._samples[i][1] = None
        self.endResetModel()

    def addSample(self, samplename):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._samples), len(self._samples))
        self._samples.append([samplename, None, 1.0, True])
        self.endInsertRows()

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...):
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._samples[row]
        self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self._samples=[]
        self.endResetModel()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex):
        flags = QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren
        sam = self._samples[index.row()]
        if index.column()==0:
            flags |= QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled
        elif index.column()>0 and sam[3]:
            flags |= QtCore.Qt.ItemIsEnabled
        return flags

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.TextColorRole:
            if (self._samples[index.row()][index.column()] is None) and (index.column()<2):
                return QtGui.QColor('gray')
            else:
                return None
        elif role in [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]:
            if index.column()<2:
                if self._samples[index.row()][index.column()] is None:
                    if role == QtCore.Qt.DisplayRole:
                        return 'Select sample...'
                    else:
                        return ''
            return self._samples[index.row()][index.column()]
        elif role == QtCore.Qt.CheckStateRole:
            if index.column()==0:
                return [QtCore.Qt.Unchecked, QtCore.Qt.Checked][self._samples[index.row()][3]]
            else:
                return None
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role==QtCore.Qt.DisplayRole:
            return ['Sample name', 'Background name', 'Background scaling'][section]
        return None

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._samples)

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 3

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...):
        if role==QtCore.Qt.EditRole:
            self._samples[index.row()][index.column()]=value
            self.dataChanged.emit(self.index(index.row(), index.column()), self.index(index.row(), index.column(), [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]))
            return True
        elif role == QtCore.Qt.CheckStateRole and index.column()==0:
            self._samples[index.row()][3]=bool(value)
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount()))
        return False

    def getBackgroundSubtractionList(self):
        return [(s[0], s[1], s[2]) for s in self._samples if s[0] is not None and s[1] is not None and s[3]]

    def getEnabledSampleNameList(self):
        return [s[0] for s in self._samples if s[0] is not None and s[3]]

class ComboBoxDelegate(QtWidgets.QStyledItemDelegate):
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        editor = QtWidgets.QComboBox(parent)
        editor.addItems(['(none)']+index.model().sampleNameList())
        return editor

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex):
        name = index.data(QtCore.Qt.EditRole)
        assert isinstance(editor, QtWidgets.QComboBox)
        editor.setCurrentIndex(editor.findText(name))

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        editor.setGeometry(option.rect)

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel, index: QtCore.QModelIndex):
        model.setData(index, editor.currentText(), QtCore.Qt.EditRole)
