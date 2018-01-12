import datetime
import pickle

from PyQt5 import QtCore


class LogBookModel(QtCore.QAbstractItemModel):
    def __init__(self, parent:QtCore.QObject, logfilename:str):
        super().__init__(parent)
        self._logdata = []
        self.logfilename = logfilename
        self.readLogFile()

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.DisplayRole:
            return str(self._logdata[index.row()][index.column()])

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._logdata)

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 3

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if role == QtCore.Qt.DisplayRole and orientation==QtCore.Qt.Horizontal:
            try:
                return ['Date', 'User', 'Message'][section]
            except IndexError:
                return '{} This should not happen'.format(section)
        return None

    def addLogEntry(self, date:datetime.datetime, username:str, message:str):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._logdata), len(self._logdata))
        self._logdata.append((date, username, message))
        self.writeLogFile()
        self.endInsertRows()

    def readLogFile(self):
        self.beginResetModel()
        self._logdata=[]
        try:
            with open(self.logfilename,'rb') as f:
                self._logdata=pickle.load(f)
        except FileNotFoundError:
            pass
        self.endResetModel()

    def writeLogFile(self):
        with open(self.logfilename, 'wb') as f:
            pickle.dump(self._logdata,f)

