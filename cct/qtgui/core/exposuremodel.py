import datetime

from PyQt5 import QtCore
from sastool.misc.errorvalue import ErrorValue

from ...core.services.filesequence import FileSequence


class HeaderModel(QtCore.QAbstractItemModel):
    # the columns you want to display. Note that the first MUST be always 'fsn' or the code will break. Sorry!
    _columns = ['fsn', 'title', 'distance', 'date', 'temperature']

    def __init__(self, parent, credo, prefix, fsnfirst, fsnlast):
        super().__init__(parent)
        self.credo = credo
        self.prefix = prefix
        self.fsnfirst = fsnfirst
        self.fsnlast = fsnlast
        self._headers = []

    def header(self, fsn: int):
        fs = self.credo.services['filesequence']
        return fs.load_header(self.prefix, fsn)

    def rowForFSN(self, fsn: int):
        return [h[0] for h in self._headers].index(fsn)

    def reloadHeaders(self):
        fs = self.credo.services['filesequence']
        assert isinstance(fs, FileSequence)
        self.beginRemoveRows(self.index(0, 0), 0, self.rowCount())
        self._headers = []
        self.endRemoveRows()
        for fsn in range(self.fsnfirst, self.fsnlast + 1):
            try:
                h = fs.load_header(self.prefix, fsn)
                hd = []
                for c in self._columns:
                    try:
                        hd.append(getattr(h, c))
                    except KeyError:
                        hd.append('N/A')
                self._headers.append(hd)
                for i, x in enumerate(self._headers[-1]):
                    if isinstance(x, ErrorValue):
                        self._headers[-1][i] = x.val
                    elif x is None:
                        self._headers[-1][i] = '--'
                    elif isinstance(x, datetime.datetime):
                        self._headers[-1][i] = str(x)
                del h
            except FileNotFoundError:
                pass

        self.beginInsertRows(self.index(0, 0), 0, len(self._headers))
        self.endInsertRows()

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._headers)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self._columns)

    def index(self, row, column, parent=None, *args, **kwargs):
        return self.createIndex(row, column, None)

    def parent(self, index: QtCore.QModelIndex = None):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role=None):
        if role == QtCore.Qt.DisplayRole:
            return self._headers[index.row()][index.column()]
        return None

    def headerData(self, column, orientation, role=None):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self._columns[column].capitalize()
        return None
