from PyQt5 import QtCore

from ....core.instrument.instrument import Instrument
from ....core.services.filesequence import FileSequence


class ScanModel(QtCore.QAbstractItemModel):
    def __init__(self, parent, credo, scanfile):
        self.credo = credo
        super().__init__(parent)
        self.scanfile = scanfile
        assert isinstance(self.credo, Instrument)

    def setScanFile(self, scanfile):
        self.beginRemoveRows(self.index(0, 0), 0, self.rowCount())
        self.endRemoveRows()
        self.scanfile = scanfile
        self.beginInsertRows(self.index(0, 0), 0, self.rowCount())
        self.endInsertRows()

    def rowCount(self, parent=None, *args, **kwargs):
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        return len(fs.scanfile_toc[self.scanfile])

    def columnCount(self, parent=None, *args, **kwargs):
        return 4

    def parent(self, index: QtCore.QModelIndex = None):
        return QtCore.QModelIndex()

    def index(self, row, column, parent=None, *args, **kwargs):
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role=None):
        if role != QtCore.Qt.DisplayRole:
            return None
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        scanindices = sorted(fs.scanfile_toc[self.scanfile].keys())
        scantoc = fs.scanfile_toc[self.scanfile][scanindices[index.row()]]
        if index.column() == 0:
            return scanindices[index.row()]
        elif index.column() == 1:
            return scantoc['cmd']
        elif index.column() == 2:
            return str(scantoc['date'])
        elif index.column() == 3:
            return str(scantoc['comment'])
        else:
            return None

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren

    def headerData(self, column, orientation, role=None):
        if orientation != QtCore.Qt.Horizontal:
            return None
        if role != QtCore.Qt.DisplayRole:
            return None
        return ['Index', 'Command', 'Date', 'Comment'][column]
