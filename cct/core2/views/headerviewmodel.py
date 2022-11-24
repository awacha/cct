import datetime
import multiprocessing.pool
from typing import Any, List, Optional, Sequence, Iterator

from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot

from ...core2.dataclasses import Header
from ...core2.instrument.components.io import IO
from ...core2.instrument.instrument import Instrument

iocomponent: Optional[IO] = None


class HeaderViewModel(QtCore.QAbstractItemModel):
    _headerdata: List[Header]
    columns: List[str] = ['fsn', 'title', 'distance', 'enddate', 'project', 'thickness', 'transmission']
    loading = Signal(bool)
    loaderpool: Optional[multiprocessing.pool.Pool] = None
    asyncresults: Optional[List[multiprocessing.pool.AsyncResult]]
    _stopLoading: bool=False

    def __init__(self):
        super().__init__()
        self._headerdata = []

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._headerdata)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self.columns)

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            value = getattr(self._headerdata[index.row()], self.columns[index.column()])
            columnname = self.columns[index.column()]
            if isinstance(value, str):
                return value
            elif isinstance(value, int):
                return str(value)
            elif isinstance(value, datetime.datetime):
                return str(value)
            elif isinstance(value, tuple) and (len(value) == 2) and isinstance(value[0], float) and isinstance(value[1],
                                                                                                               float):
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
        elif role == QtCore.Qt.ItemDataRole.UserRole:
            return self._headerdata[index.row()]

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Orientation.Horizontal) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return self.columns[section]

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled

    def reload(self, fsns: Sequence[int]):
        if self.loaderpool is not None:
            raise RuntimeError('Another reload process is running in the background')
        self.loaderpool = multiprocessing.Pool(multiprocessing.cpu_count(), initializer=self._initloaderpool,
                                               initargs=(Instrument.instance().config.asdict(),))
        prefix = Instrument.instance().config['path']['prefixes']['crd']
        self.asyncresults = [self.loaderpool.apply_async(self._loadheader, (prefix, fsn, True)) for fsn in
                             fsns]
        self.beginResetModel()
        self._headerdata = []
        self.endResetModel()
        self.startTimer(100, QtCore.Qt.TimerType.VeryCoarseTimer)
        self.loading.emit(True)

    @staticmethod
    def _initloaderpool(config):
        global iocomponent
        iocomponent = IO(config=config, instrument=None)

    @staticmethod
    def _loadheader(prefix: int, fsn: int, raw: bool) -> Optional[Header]:
        global iocomponent
        try:
            return iocomponent.loadHeader(prefix, fsn, raw)
        except FileNotFoundError:
            return None

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        ready = [asyncresult for asyncresult in self.asyncresults if asyncresult.ready()]
        if not ready:
            return
        self.asyncresults = [a for a in self.asyncresults if a not in ready]
        self.beginResetModel()
        self._headerdata.extend([a.get() for a in ready if a.get() is not None])
        self.endResetModel()
        if self.loaderpool is None:
            # user break
            if not [a for a in self.asyncresults if a.ready()]:
                # there are no more tasks ready:
                self.killTimer(timerEvent.timerId())
                self.asyncresults = None
                self.beginResetModel()
                self._headerdata = sorted(self._headerdata, key=lambda h: h.fsn)
                self.endResetModel()
                self.loading.emit(False)
            else:
                # wait one more turn.
                pass
        elif not self.asyncresults:
            self.killTimer(timerEvent.timerId())
            self.loaderpool.close()
            self.loaderpool.join()
            self.loaderpool = None
            self.asyncresults = None
            self.beginResetModel()
            self._headerdata = sorted(self._headerdata, key=lambda h: h.fsn)
            self.endResetModel()
            self.loading.emit(False)

    def stopLoading(self):
        self.loaderpool.terminate()
        self.loaderpool.join()
        self.loaderpool = None

    def isLoading(self) -> bool:
        return self.loaderpool is not None

    def __iter__(self) -> Iterator[Header]:
        yield from self._headerdata

    def __len__(self):
        return len(self._headerdata)