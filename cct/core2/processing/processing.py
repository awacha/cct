import enum
import logging
from typing import List, Tuple, Any, Optional

import numpy as np
import h5py
from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot

from .loader import Loader
from .settings import ProcessingSettings
from .tasks.headers import HeaderStore
from .tasks.merging import Merging
from .tasks.resultsmodel import ResultsModel
from .tasks.subtraction import Subtraction
from .tasks.summarization import Summarization

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ProcessingStatus(enum.Enum):
    Idle = 'idle'
    LoadingHeaders = 'loading headers'
    Processing = 'processing'
    SubtractingBackground = 'subtracting background'
    MergingDistances = 'merging distances'


class Processing(QtCore.QAbstractItemModel):
    status: ProcessingStatus = ProcessingStatus.Idle
    settings: ProcessingSettings

    # parts
    headers: HeaderStore
    summarization: Summarization
    subtraction: Subtraction
    results: ResultsModel
    merging: Merging

    resultItemChanged = Signal(str, str)

    """The main class of the processing subsystem"""

    def __init__(self, filename: str):
        super().__init__()
        self.settings = ProcessingSettings(filename)
        self.headers = HeaderStore(self, self.settings)
        self.headers.finished.connect(self.onTaskFinished)
        self.summarization = Summarization(self, self.settings)
        self.summarization.finished.connect(self.onTaskFinished)
        self.summarization.itemChanged.connect(self.resultItemChanged)
        self.subtraction = Subtraction(self, self.settings)
        self.subtraction.finished.connect(self.onTaskFinished)
        self.subtraction.itemChanged.connect(self.resultItemChanged)
        self.results = ResultsModel(self, self.settings)
        self.merging = Merging(self, self.settings)
        self.merging.finished.connect(self.onTaskFinished)
        self.merging.itemChanged.connect(self.resultItemChanged)
        self.settings.badfsnsChanged.connect(self.onBadFSNsChanged)

    @Slot()
    def onBadFSNsChanged(self):
        self.headers.badfsnschanged()

    def isIdle(self):
        return self.headers.isIdle() and self.summarization.isIdle() and self.subtraction.isIdle()

    @Slot(bool)
    def onTaskFinished(self, success: bool):
        if self.sender() is self.headers:
            # headers have been loaded
            logger.debug('Headers have been loaded.')
            self.summarization.clear()
            for samplename in sorted({h.title for h in self.headers}):
                sampleheaders = [h for h in self.headers if h.title == samplename]
                for distance in sorted({h.distance[0] for h in sampleheaders}):
                    logger.debug(f'Adding {samplename=}, {distance=} to summarization')
                    fsns = [h.fsn for h in sampleheaders if (h.distance[0] == distance)]
                    logger.debug(f'Got {len(fsns)} FSNS')
                    self.summarization.addSample(samplename, distance, fsns)
                    logger.debug(f'Added {samplename=}. {distance=}')
            logger.debug('Summarization updated.')
        elif self.sender() is self.summarization:
            # summarization done
            self.headers.badfsnschanged()
            self.results.reload()
        elif self.sender() is self.subtraction:
            self.results.reload()
        elif self.sender() is self.merging:
            self.results.reload()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self.fsnranges)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 4

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if index.column() < 3:
            if role == QtCore.Qt.ItemDataRole.DisplayRole:
                return str(self.fsnranges[index.row()][index.column()])
            elif role == QtCore.Qt.ItemDataRole.EditRole:
                return self.fsnranges[index.row()][index.column()]
            else:
                return None
        elif (index.column() == 3) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return ', '.join(self.fsnranges[index.row()][3]) if self.fsnranges[index.row()][3] is not None else ''
        elif (index.column() == 3) and (role == QtCore.Qt.ItemDataRole.EditRole):
            return ', '.join(self.fsnranges[index.row()][3]) if self.fsnranges[index.row()][3] is not None else ''
        else:
            return None



    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Orientation.Horizontal) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return ['Start', 'End', 'Description', 'Load only these samples'][section]

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsEditable | QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        fsnmin, fsnmax, description, onlysamples = self.fsnranges[index.row()]
        if index.column() == 0:
            try:
                self.fsnranges[index.row()] = (int(value), fsnmax, description, onlysamples)
            except ValueError:
                return False
        elif index.column() == 1:
            try:
                self.fsnranges[index.row()] = (fsnmin, int(value), description, onlysamples)
            except ValueError:
                return False
        elif index.column() == 2:
            try:
                self.fsnranges[index.row()] = (fsnmin, fsnmax, str(value), onlysamples)
            except ValueError:
                return False
        elif index.column() == 3:
            assert isinstance(value, str)
            if not value.strip():
                value = None
            else:
                value = [x.strip() for x in value.split(',')]
            try:
                self.fsnranges[index.row()] = (fsnmin, fsnmax, description, value)
            except ValueError:
                return False
        else:
            assert False
        self.dataChanged.emit(index, index)
        self.settings.emitSettingsChanged()
        return True

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.insertRows(row, 1, QtCore.QModelIndex())

    def insertRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginInsertRows(QtCore.QModelIndex(), row, row + count - 1)
        self.fsnranges = self.fsnranges[:row] + [(0, 0, '', None)] * count + self.fsnranges[row:]
        self.endInsertRows()
        self.settings.emitSettingsChanged()
        return True

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.removeRows(row, 1, QtCore.QModelIndex())

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginRemoveRows(QtCore.QModelIndex(), row, row + count - 1)
        del self.fsnranges[row:row + count]
        self.endRemoveRows()
        self.settings.emitSettingsChanged()
        return True

    def modelReset(self) -> None:
        self.beginResetModel()
        self.fsnranges = []
        self.endResetModel()
        self.settings.emitSettingsChanged()

    @property
    def fsnranges(self) -> List[Tuple[int, int, str, Optional[List[str]]]]:
        return self.settings.fsnranges

    @fsnranges.setter
    def fsnranges(self, newvalue: List[Tuple[int, int, str, Optional[List[str]]]]):
        self.beginResetModel()
        self.settings.fsnranges = newvalue
        self.endResetModel()
        self.settings.emitSettingsChanged()

    def save(self, filename):
        self.settings.save(filename)

    @classmethod
    def fromFile(cls, filename) -> "Processing":
        p = cls(filename)
        return p

    def saveAs(self, filename):
        with h5py.File(filename, 'w') as h5out:
            with self.settings.h5io.reader() as h5:
                def copy(path: str):
                    if isinstance(h5.get(path, getlink=True), h5py.SoftLink):
                        # do not copy links at this stage
                        return
                    if isinstance(h5.get(path, getclass=True), h5py.Group):
                        grp = h5out.require_group(path)
                        grp.attrs.update(h5.get(path).attrs)
                    elif isinstance(h5.get(path, getclass=True), h5py.Dataset):
                        ds = h5.get(path)
                        dsnew = h5out.create_dataset(path, shape=ds.shape, dtype=ds.dtype, data=np.array(ds),
                                                     compression=ds.compression, compression_opts=ds.compression_opts)
                        dsnew.attrs.update(ds.attrs)
                    else:
                        raise ValueError(path)

                def copysoftlinks(path: str):
                    if isinstance(h5.get(path, getlink=True), h5py.SoftLink):
                        h5out[path] = h5py.SoftLink(h5.get(path, getlink=True).path)

                h5.visit(copy)
                h5.visit(copysoftlinks)

    def loader(self) -> Loader:
        return self.settings.loader()
