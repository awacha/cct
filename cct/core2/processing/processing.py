import itertools
from typing import List, Optional, Tuple, Any
import enum

from .h5io import ProcessingH5File
from .tasks.summarization import Summarization
from PyQt5 import QtCore
from .tasks.headers import HeaderStore
from .settings import ProcessingSettings


class ProcessingStatus(enum.Enum):
    Idle = 'idle'
    LoadingHeaders = 'loading headers'
    Processing = 'processing'
    SubtractingBackground = 'subtracting background'
    MergingDistances = 'merging distances'


class Processing(QtCore.QAbstractItemModel):
    status: ProcessingStatus = ProcessingStatus.Idle
    filename: Optional[str] = None
    settings: ProcessingSettings
    resultviews: List
    h5io: ProcessingH5File

    # parts
    headers : HeaderStore
    summarization: Summarization
#    backgroundsubtraction: BackgroundSubtraction
#    merging: Merging
#    reporting: Reporting


    """The main class of the processing subsystem"""
    def __init__(self):
        super().__init__()
        self.settings = ProcessingSettings()
        self.headers = HeaderStore(self.settings)
        self.headers.finished.connect(self.onTaskFinished)
        self.summarization = Summarization(self.settings)
        self.summarization.finished.connect(self.onTaskFinished)

    def isIdle(self):
        return self.headers.isIdle() and self.summarization.isIdle()

    def reloadHeaders(self):
        if not self.isIdle():
            raise RuntimeError('Cannot reload headers: working.')
        self.headers.start(
            list(
                itertools.chain(
                    *[range(fsnmin, fsnmax+1) for fsnmin, fsnmax in self.fsnranges]
                )
            )
        )

    def startSummarizing(self):
        if not self.isIdle():
            raise RuntimeError('Cannot start processing: not idle.')
        self.summarization.start()

    def startBackgroundSubtraction(self):
        pass

    def stopCurrentWork(self):
        pass

    def startMerging(self):
        pass

    def addBackgroundPair(self, sample: str, background: str, distance: Optional[float] = None):
        pass

    def addMerging(self, sample: str, qmin: str, qmax: str):
        pass

    def fsnsForSampleAndDistance(self, samplename: str, distance: float, includebad: bool=False):
        pass

    def onTaskFinished(self, success: bool):
        if (self.sender() is self.headers) and success:
            # headers have been loaded
            self.summarization.clear()
            for samplename in sorted({h.title for h in self.headers}):
                for distance in sorted({h.distance for h in self.headers if h.title == samplename}):
                    self.summarization.addSample(samplename, distance, [h.fsn for h in self.headers if (h.title == samplename) and (h.distance == distance)])
        elif (self.sender() is self.summarization) and success:
            # summarization done
            pass

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self.fsnranges)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 2

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if role == QtCore.Qt.DisplayRole:
            return str(self.fsnranges[index.row()][index.column()])
        elif role == QtCore.Qt.EditRole:
            return self.fsnranges[index.row()][index.column()]
        else:
            return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Start', 'End'][section]

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        fsnmin, fsnmax = self.fsnranges[index.row()]
        if index.column() == 0:
            try:
                self.fsnranges[index.row()] = (int(value), fsnmax)
            except ValueError:
                return False
        elif index.column() == 1:
            try:
                self.fsnranges[index.row()] = (fsnmin, int(value))
            except ValueError:
                return False
        else:
            assert False
        self.dataChanged.emit(index, index)
        return True

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.insertRows(row, 1, QtCore.QModelIndex())

    def insertRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginInsertRows(QtCore.QModelIndex(), row, row+count-1)
        self.fsnranges = self.fsnranges[:row] + [(0,0)]*count + self.fsnranges[row:]
        self.endInsertRows()
        return True

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.removeRows(row, 1, QtCore.QModelIndex())

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginRemoveRows(QtCore.QModelIndex(), row, row+count-1)
        del self.fsnranges[row:row+count]
        self.endRemoveRows()
        return True

    def modelReset(self) -> None:
        self.beginResetModel()
        self.fsnranges = []
        self.endResetModel()

    @property
    def fsnranges(self) -> List[Tuple[int, int]]:
        return self.settings.fsnranges

    @fsnranges.setter
    def fsnranges(self, newvalue: List[Tuple[int, int]]):
        self.settings.fsnranges = newvalue

    def save(self, filename):
        self.settings.save(filename)

    @classmethod
    def fromFile(cls, filename) -> "Processing":
        p = cls()
        p.settings.load(filename)
        return p
