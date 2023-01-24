import pickle
from typing import Tuple, List, Iterable, Any
import logging

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Slot

from .samples_ui import Ui_WizardPage
from ......core2.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Model(QtCore.QAbstractItemModel):
    _data: List[Tuple[str, float, int]]
    exposuretime: float=300
    exposurecount: int=1

    def __init__(self):
        self._data = []
        super().__init__()

    def setDefaultExposureTime(self, exptime: float):
        self.exposuretime = exptime

    def setDefaultExposureCount(self, expcount: int):
        self.exposurecount = expcount

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 3

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if not index.isValid():
            return QtCore.Qt.ItemFlag.ItemIsDropEnabled | QtCore.Qt.ItemFlag.ItemIsDropEnabled
        elif index.column() == 0:
            return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsDropEnabled
        else:
            return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsDropEnabled | QtCore.Qt.ItemFlag.ItemIsEditable

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if (index.column() == 0) and (role in [QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole]):
            return self._data[index.row()][0]
        elif (index.column() == 1) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return f'{self._data[index.row()][1]:.2f} sec'
        elif (index.column() == 1) and (role == QtCore.Qt.ItemDataRole.EditRole):
            return self._data[index.row()][1]
        elif (index.column() == 2) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return f'{self._data[index.row()][2]:d}'
        elif (index.column() == 2) and (role == QtCore.Qt.ItemDataRole.EditRole):
            return self._data[index.row()][2]
        else:
            return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if role != QtCore.Qt.ItemDataRole.EditRole:
            logger.warning(f'setdata(row={index.row()}, column={index.column()}, {value=}, {type(value)=} role={role} != EditRole)')
            return False
        data = self._data[index.row()]
        if index.column() == 0:
            self._data[index.row()] = value, data[1], data[2]
        elif (index.column() == 1) and (value > 0):
            self._data[index.row()] = data[0], float(value), data[2]
        elif (index.column() == 2) and (value > 0):
            self._data[index.row()] = data[0], data[1], int(value)
        else:
            return False
        self.dataChanged.emit(index, index)
        return True

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.insertRows(row, 1, parent)

    def insertRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginInsertRows(parent, row, row+count-1)
        self._data = self._data[:row] + [('', self.exposuretime, self.exposurecount) for i in range(count)] + self._data[row:]
        self.endInsertRows()
        return True

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginRemoveRows(parent, row, row+count-1)
        self._data = self._data[:row] + self._data[row+count:]
        self.endRemoveRows()
        return True

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.removeRows(row, 1, parent)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Orientation.Horizontal) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return ['Sample', 'Exposure time', 'Exposure count'][section]
        return None

    def dropMimeData(self, data: QtCore.QMimeData, action: QtCore.Qt.DropAction, row: int, column: int, parent: QtCore.QModelIndex) -> bool:
        logger.debug(f'dropMimeData({data.formats()}, {action=}, {row=}, {column=}, {parent.isValid()=}')
        if parent.isValid():
            return False
        if row < 0:
            row = len(self._data)
        if data.hasFormat('application/x-cctsequenceexposurelist'):
            lis = pickle.loads(data.data('application/x-cctsequenceexposurelist'))
            logger.debug(f'Adding {len(lis)} exposurelist elements')
            if not lis:
                return False
            for r_ in [r for r, l in lis]:
                self._data[r_]='', -1, -1
            self.beginInsertRows(parent, row, row+len(lis)-1)
            self._data = self._data[:row] + [l for r,l in lis] + self._data[row:]
            self.endInsertRows()
            while (rowstoremove := [r for r, d in enumerate(self._data) if d == ('', -1, -1)]):
                self.removeRow(rowstoremove[0], QtCore.QModelIndex())
        elif data.hasFormat('application/x-cctsamplelist'):
            lis = pickle.loads(data.data('application/x-cctsamplelist'))
            logger.debug(f'Adding {len(lis)} samples')
            if not lis:
                return False
            self.beginInsertRows(parent, row, row+len(lis)-1)
            self._data = self._data[:row] + [(s.title, self.exposuretime, self.exposurecount) for s in lis] + self._data[row:]
            self.endInsertRows()
        else:
            return False
        return True

    def supportedDragActions(self) -> QtCore.Qt.DropAction:
        return QtCore.Qt.DropAction.MoveAction

    def supportedDropActions(self) -> QtCore.Qt.DropAction:
        return QtCore.Qt.DropAction.CopyAction | QtCore.Qt.DropAction.MoveAction

    def mimeData(self, indexes: Iterable[QtCore.QModelIndex]) -> QtCore.QMimeData:
        md = QtCore.QMimeData()
        rows = {i.row() for i in indexes}
        md.setData('application/x-cctsequenceexposurelist', pickle.dumps([(r, self._data[r]) for r in rows]))
        return md

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def mimeTypes(self) -> List[str]:
        return ['application/x-cctsequenceexposurelist', 'application/x-cctsamplelist']

    def exposures(self) -> List[Tuple[str, float, int]]:
        return self._data

    def setExpTimes(self):
        for i in range(len(self._data)):
            self._data[i] = self._data[i][0], self.exposuretime, self._data[i][2]
        self.dataChanged.emit(
            self.index(0, 1, QtCore.QModelIndex()),
            self.index(len(self._data), 1, QtCore.QModelIndex())
        )

    def setExpCounts(self):
        for i in range(len(self._data)):
            self._data[i] = self._data[i][0], self._data[i][1], self.exposurecount
        self.dataChanged.emit(
            self.index(0, 2, QtCore.QModelIndex()),
            self.index(len(self._data), 2, QtCore.QModelIndex())
        )


class SamplesPage(QtWidgets.QWizardPage, Ui_WizardPage):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, WizardPage):
        super().setupUi(WizardPage)
        instrument = Instrument.instance()
        self.sampleListView.setModel(instrument.samplestore.sortedmodel)
        self.sampleListView.setSelectionModel(QtCore.QItemSelectionModel(self.sampleListView.model(), self.sampleListView))
        self.exposureTreeView.setModel(Model())
        self.exposureTreeView.setSelectionModel(QtCore.QItemSelectionModel(self.exposureTreeView.model(), self.exposureTreeView))
        self.addSampleToolButton.clicked.connect(self.onAddSample)
        self.removeSamplesToolButton.clicked.connect(self.onRemoveSamples)
        self.clearExposureListToolButton.clicked.connect(self.onClearExposureList)
        self.exposureTimeDoubleSpinBox.valueChanged.connect(self.exposureTreeView.model().setDefaultExposureTime)
        self.exposureCountSpinBox.valueChanged.connect(self.exposureTreeView.model().setDefaultExposureCount)
        self.setExpCountToolButton.clicked.connect(self.exposureTreeView.model().setExpCounts)
        self.setExpTimeToolButton.clicked.connect(self.exposureTreeView.model().setExpTimes)
        self.registerField('orderSamples', self.orderSamplesCheckBox, 'checked', 'toggled')

    def exposures(self) -> List[Tuple[str, float, int]]:
        return self.exposureTreeView.model().exposures()

    @Slot()
    def onAddSample(self):
        logger.debug(f'Adding {len(self.sampleListView.selectedIndexes())} samples')
        for index in self.sampleListView.selectedIndexes():
            samplename = index.data(QtCore.Qt.ItemDataRole.DisplayRole)
            logger.debug(f'Adding sample {samplename}')
            model = self.exposureTreeView.model()
            model.insertRow(model.rowCount(QtCore.QModelIndex()) + 1, QtCore.QModelIndex())
            model.setData(model.index(model.rowCount(QtCore.QModelIndex())-1, 0, QtCore.QModelIndex()), samplename, QtCore.Qt.ItemDataRole.EditRole)
        self.sampleListView.selectionModel().clearSelection()

    @Slot()
    def onRemoveSamples(self):
        while (indexlist := self.exposureTreeView.selectionModel().selectedRows(0)):
            self.exposureTreeView.model().removeRow(indexlist[0].row(), QtCore.QModelIndex())

    @Slot()
    def onClearExposureList(self):
        self.exposureTreeView.model().clear()


