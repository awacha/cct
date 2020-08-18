import logging
from typing import Any, Dict, Tuple, List, Optional

from PyQt5 import QtCore, QtWidgets

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DECIMALS = 6


class PeakModel(QtCore.QAbstractItemModel):
    _peakdata: List[Tuple[str, float, float]]

    def __init__(self, peakdata: Optional[List[Tuple[str, float, float]]]=None):
        super().__init__()
        self._peakdata = peakdata if peakdata is not None else []

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 3

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._peakdata)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Name', 'Value (1/nm)', 'Uncertainty (1/nm)'][section]
        else:
            return None

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        logger.debug('Rowcount: {}'.format(self.rowCount()))
        logger.debug('Index: {}, {}'.format(index.row(), index.column()))
        logger.debug(
            'Peakdata [{}]: {}. Rowcount: {}'.format(index.row(), self._peakdata[index.row()], self.rowCount()))
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return self._peakdata[index.row()][0]
            else:
                return '{{:.{:d}f}}'.format(DECIMALS).format(self._peakdata[index.row()][index.column()])
        elif role == QtCore.Qt.EditRole:
            return self._peakdata[index.row()][index.column()]
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...):
        self._peakdata[index.row()][index.column()] = value
        self.dataChanged.emit(self.index(index.row(), index.column(), None),
                              self.index(index.row(), index.column(), None),
                              [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
        return True

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...):
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._peakdata[row]
        self.endRemoveRows()

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...):
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._peakdata.insert(row, ['Untitled', 0., 0.])
        self.endInsertRows()

    def fromDict(self, dic: Dict[str, Dict[str, float]]):
        self.beginResetModel()
        self._peakdata = []
        for k in sorted(dic):
            self._peakdata.append([k, dic[k]['val'], dic[k]['err']])
        self.endResetModel()

    def toDict(self) -> Dict[str, Dict[str, float]]:
        return {k: {'val': v, 'err': e} for k, v, e in self._peakdata}

    def toList(self) -> List[Tuple[str, float, float]]:
        return list(self._peakdata)


class DoubleSpinBoxDelegate(QtWidgets.QStyledItemDelegate):
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex):
        editor = QtWidgets.QDoubleSpinBox(parent)
        editor.setMinimum(0)
        editor.setMaximum(10000)
        editor.setDecimals(DECIMALS)
        return editor

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex):
        value = index.data(QtCore.Qt.EditRole)
        assert isinstance(editor, QtWidgets.QDoubleSpinBox)
        editor.setValue(value)

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex):
        editor.setGeometry(option.rect)

    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel, index: QtCore.QModelIndex):
        model.setData(index, editor.value(), QtCore.Qt.EditRole)
