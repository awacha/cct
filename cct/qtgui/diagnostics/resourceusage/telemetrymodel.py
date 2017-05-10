from PyQt5 import QtCore

from ....core.services.telemetry import TelemetryInfo


class TelemetryModel(QtCore.QAbstractItemModel):
    def __init__(self):
        QtCore.QAbstractItemModel.__init__(self, None)
        self._tminfo=[]

    def update_telemetry(self, tm:TelemetryInfo):
        self.beginResetModel()
        self._tminfo=[
            ('Memory usage (GB)','{:.3f}'.format(tm.memusage/1000)),
            ('User time (sec)',tm.usertime),
            ('System time (sec)',tm.systemtime),
            ('Page faults w/o I/O',tm.pagefaultswithoutio),
            ('Page faults w/ I/O',tm.pagefaultswithio),
            ('FS input',tm.fsinput),
            ('FS output',tm.fsoutput),
            ('Vol. ctx switches',tm.voluntarycontextswitches),
            ('Invol. ctx switches',tm.involuntarycontextswitches),
        ]
        for attr in tm.user_attributes():
            self._tminfo.append((attr, getattr(tm, attr)))
        self.endResetModel()

    def columnCount(self, parent: QtCore.QModelIndex = None):
        return 2

    def rowCount(self, parent: QtCore.QModelIndex = None):
        return len(self._tminfo)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return None
        return self._tminfo[index.row()][index.column()]

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = None):
        return self.createIndex(row, column, None)

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal and role==QtCore.Qt.DisplayRole:
            return ['Variable','Value'][section]
