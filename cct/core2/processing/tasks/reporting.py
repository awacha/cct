import enum
from ctypes import Union
from typing import Tuple, List, Any

from PySide6 import QtCore, QtGui

from .task import ProcessingTask
from ..settings import ProcessingSettings
from ..calculations.resultsentry import CurveFileType, PatternFileType, CorMatFileType




class ReportingJobData:
    filetype: Union[CurveFileType, PatternFileType, CorMatFileType, ReportFileType]
    samplename: str
    distancekey: str
    path: str


class Reporting(ProcessingTask):
    _data: List[ReportingJobData]

    def __init__(self, processing: "Processing", settings: ProcessingSettings):
        self._data = []
        super().__init__(processing=processing, settings=settings)

    def _start(self):
        pass

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)
    
    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 3
    
    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsSelectable
    
    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()
    
    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)
    
    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        d = self._data[index.row()]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return d.samplename
            elif index.column() == 1:
                return d.distancekey
            elif index.column() == 2:
                return d.path
        elif (role == QtCore.Qt.ItemDataRole.DecorationRole) and (index.column() == 0):
            if isinstance(d.filetype, CurveFileType):
                return QtGui.QIcon(':/icons/saxscurve.svg')
            elif isinstance(d.filetype, PatternFileType):
                return QtGui.QIcon(':/icons/saxspattern.svg')
            elif isinstance(d.filetype, CorMatFileType):
                return QtGui.QIcon(':/icons/outliers.svg')
            elif d.filetype is ReportFileType.DOCX:
                return QtGui.QIcon.fromTheme('x-office-writer')
            elif d.filetype is ReportFileType.XLSX:
                return QtGui.QIcon.fromTheme('x-office-spreadsheet')
    
    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (role==QtCore.Qt.ItemDataRole.DisplayRole) and (orientation == QtCore.Qt.Orientation.Horizontal):
            return ['Sample name', 'Distance', 'Output path'][section]

