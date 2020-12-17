import datetime
import multiprocessing
import os
import logging
from typing import Any, List, Final, Optional, Sequence, Iterator, Tuple

from PyQt5 import QtCore

from ..settings import ProcessingSettings
from .task import ProcessingTask, ProcessingStatus
from ...dataclasses import Header

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HeaderStore(ProcessingTask):

    _data: List[Header]
    _data_being_loaded: Optional[List[Optional[Header]]] = None
    columns: Final[List[str]] = ['fsn', 'title', 'distance', 'enddate', 'project', 'thickness', 'transmission']

    def __init__(self, processing: "Processing", settings: ProcessingSettings):
        self._data = []
        super().__init__(processing, settings)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self.columns)

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if (index.column() == 0) and (role == QtCore.Qt.CheckStateRole):
            if value == QtCore.Qt.Checked:
                self.settings.markAsBad(self._data[index.row()].fsn)
            elif value == QtCore.Qt.Unchecked:
                self.settings.markAsGood(self._data[index.row()].fsn)
            else:
                raise ValueError(f'Invalid check state: {value}')
            self.dataChanged.emit(index, index, [QtCore.Qt.CheckStateRole])
            return True
        return False

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if role == QtCore.Qt.DisplayRole:
            value = getattr(self._data[index.row()], self.columns[index.column()])
            columnname = self.columns[index.column()]
            if isinstance(value, str):
                return value
            elif isinstance(value, int):
                return str(value)
            elif isinstance(value, datetime.datetime):
                return str(value)
            elif (isinstance(value, tuple)
                  and (len(value) == 2)
                  and isinstance(value[0], float)
                  and isinstance(value[1], float)):
                if columnname == 'distance':
                    return f'{value[0]:.2f} \xb1 {value[1]:.2f}'
                elif columnname == 'thickness':
                    return f'{value[0]:.3f} \xb1 {value[1]:.3f}'
                elif columnname == 'transmission':
                    return f'{value[0]:.4f} \xb1 {value[1]:.4f}'
                else:
                    return f'{value[0]:g} \xb1 {value[1]:g}'
            else:
                return str(value)
        elif role == QtCore.Qt.UserRole:
            return self._data[index.row()]
        elif (role == QtCore.Qt.CheckStateRole) and (index.column() == 0):
            return QtCore.Qt.Checked if (self._data[index.row()].fsn in self.settings.badfsns) else QtCore.Qt.Unchecked
        else:
            return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return self.columns[section]

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if index.column() == 0:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | \
                   QtCore.Qt.ItemIsUserCheckable
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled

    def _start(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()
        fsns = list(self.settings.fsns())
        self._data_being_loaded=[None] * len(fsns)
        for i, fsn in enumerate(fsns):
            self._submitTask(self._loadheader, i, rootdir=os.path.join(self.settings.rootpath, self.settings.eval2dsubpath), prefix=self.settings.prefix, fsn=fsn, fsndigits=self.settings.fsndigits)

    @staticmethod
    def _loadheader(h5file: str, h5lock, jobid, messagequeue, stopEvent, rootdir: str, prefix: str, fsn: int, fsndigits) -> Tuple[int, Optional[Header]]:
        filename = f'{prefix}_{fsn:0{fsndigits}d}.pickle'
        # first try the header in the root directory
        try:
            return jobid, Header(filename = os.path.join(rootdir, filename))
        except FileNotFoundError:
            pass
        # if not successful, try the 'prefix' subfolder
        try:
            return jobid, Header(filename = os.path.join(rootdir, prefix, filename))
        except FileNotFoundError:
            pass

        # if this is also unsuccessful, resort to a slower, recursive search
        def findrecursive(folder:str, fn: str):
            try:
                return Header(filename=os.path.join(folder, fn))
            except FileNotFoundError:
                for d in [d for d in os.listdir(folder) if os.path.isdir(d)]:
                    try:
                        return findrecursive(d, fn)
                    except FileNotFoundError:
                        continue
                raise FileNotFoundError(fn)
        try:
            return jobid, findrecursive(rootdir, filename)
        except FileNotFoundError:
            return jobid, None

    def onAllBackgroundTasksFinished(self):
        self.beginResetModel()
        self._data = [h for h in self._data_being_loaded if h is not None]
        self._data_being_loaded = None
        self.endResetModel()

    def onBackgroundTaskFinished(self, result: Tuple[int, Optional[Header]]):
        jobid, header = result
        if header is None:
            return
        assert isinstance(header, Header)
        self._data_being_loaded[jobid]=header
        super().onBackgroundTaskFinished(result)

    def stop(self):
        super().stop()
        self._pool.terminate()

    def __iter__(self) -> Iterator[Header]:
        yield from self._data

    def __len__(self):
        return len(self._data)

    def badfsnschanged(self):
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount(), 0), [QtCore.Qt.CheckStateRole])