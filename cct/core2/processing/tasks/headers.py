import datetime
import enum
import multiprocessing
import os
import logging
from typing import Any, List, Final, Optional, Sequence, Iterator

from PyQt5 import QtCore

from ..settings import ProcessingSettings
from .task import ProcessingTask, ProcessingStatus
from ...dataclasses import Header

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HeaderLoaderStatus(enum.Enum):
    Idle = 'idle'
    Stopping = 'user stop requested'
    Loading = 'Loading headers'


class HeaderStore(ProcessingTask):

    _data: List[Header]
    columns: Final[List[str]] = ['fsn', 'title', 'distance', 'enddate', 'project', 'thickness', 'transmission']
    loaderpool: Optional[multiprocessing.pool.Pool] = None
    asyncresults: Optional[List[multiprocessing.pool.AsyncResult]]
    _stopLoading: bool = False

    def __init__(self, settings: ProcessingSettings):
        self._data = []
        super().__init__(settings)

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
            logger.debug(f'Getting header field {self.columns[index.column()]} of header #{index.row()}')
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
            return QtCore.Qt.Checked if (self._data[index.row()] in self.settings.badfsns) else QtCore.Qt.Unchecked
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

    def start(self, fsns: Sequence[int]):
        if not self.isIdle():
            raise RuntimeError('Another reload process is running in the background')
        self.status = HeaderLoaderStatus.Loading
        assert self._pool is None
        self._pool = multiprocessing.Pool()
        self._asyncresults = [self._pool.apply_async(
            self._loadheader,
            (os.path.join(self.settings.rootpath, self.settings.eval2dsubpath),
             self.settings.prefix, fsn, self.settings.fsndigits)) for fsn in fsns]
        self.beginResetModel()
        self._data = []
        self.endResetModel()
        self.startTimer(100, QtCore.Qt.VeryCoarseTimer)
        self.started.emit()

    @staticmethod
    def _loadheader(rootdir: str, prefix: str, fsn: int, fsndigits) -> Header:
        filename = f'{prefix}_{fsn:0{fsndigits}d}.pickle'
        # first try the header in the root directory
        try:
            return Header(filename = os.path.join(rootdir, filename))
        except FileNotFoundError:
            pass
        # if not successful, try the 'prefix' subfolder
        try:
            return Header(filename = os.path.join(rootdir, prefix, filename))
        except FileNotFoundError:
            pass

        # if this is also unsuccessful, resort to a slower, recursive search
        def findrecursive(folder:str, fn: str):
            try:
                return Header(filename=os.path.join(folder, fn))
            except FileNotFoundError:
                for d in [d for d in os.listdir(folder) if os.path.isdir(d)]:
                    try:
                        return findrecursive(d,fn)
                    except FileNotFoundError:
                        continue
                raise FileNotFoundError(fn)
        return findrecursive(rootdir, filename)

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        ready = [asyncresult for asyncresult in self._asyncresults if asyncresult.ready()]
        if not ready:
            return
        self._asyncresults = [a for a in self._asyncresults if a not in ready]
        self.beginResetModel()
        self._data.extend([a.get() for a in ready if a.get() is not None])
        self.endResetModel()
        if ((not self._asyncresults) or
                (self.status == ProcessingStatus.Stopping) and not [ar for ar in self._asyncresults if ar.ready()]):
            # no more running tasks. OR (user stop requested AND no more finished tasks to gather results from)
            self.killTimer(timerEvent.timerId())
            self._pool.close()
            self._pool.join()
            self._pool = None
            self._asyncresults = None
            self.beginResetModel()
            self._data = sorted(self._data, key=lambda h: h.fsn)
            self.endResetModel()
            success = self.status != ProcessingStatus.Stopping
            self.status = ProcessingStatus.Idle
            self.finished.emit(success)

    def stop(self):
        if self.isIdle():
            return
        self.status = ProcessingStatus.Stopping
        self._pool.terminate()

    def __iter__(self) -> Iterator[Header]:
        yield from self._data

    def __len__(self):
        return len(self._data)

    def badfsnschanged(self):
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount(), 0), [QtCore.Qt.CheckStateRole])