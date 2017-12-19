from PyQt5 import QtCore

from ....core.instrument.instrument import Instrument
from ....core.services.accounting import Accounting, Project


class ProjectsModel(QtCore.QAbstractItemModel):
    def __init__(self, credo:Instrument):
        super().__init__(None)
        self._projects=[]
        self.credo = credo
        a = self.credo.services['accounting']
        assert isinstance(a, Accounting)
        self._accounting_connections = [a.connect('project-changed', self._updatelist)]
        self._updatelist(a)

    def _updatelist(self, accounting:Accounting):
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        a = self.credo.services['accounting']
        assert isinstance(a, Accounting)
        return len(a.get_projectids())

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 2

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        ids = sorted(self.credo.services['accounting'].get_projectids())
        prj = self.credo.services['accounting'].get_project(ids[index.row()])
        assert isinstance(prj, Project)
        if role != QtCore.Qt.DisplayRole:
            return None
        if index.column() == 0:
            return prj.projectid
        elif index.column() == 1:
            return prj.projectname
        else:
            return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation== QtCore.Qt.Horizontal and role==QtCore.Qt.DisplayRole:
            return ['ID', 'Title'][section]

    def cleanup(self):
        for c in self._accounting_connections:
            self.credo.services['accounting'].disconnect(c)
        self._accounting_connections=[]
