import typing

from PyQt5 import QtCore

from ....core.instrument.instrument import Instrument


class ConfigStore(QtCore.QAbstractItemModel):
    def __init__(self, credo:Instrument):
        super().__init__(None)
        self.credo = credo
        self._paths=[]
        self._indices = {}
        self._credo_connection = []
        self.destroyed.connect(self.onDestroyed)
        self.credo.connect('config-changed', self.onConfigChanged)

    def onConfigChanged(self, credo:Instrument):
        self.beginResetModel()
        self.endResetModel()

    def onDestroyed(self):
        try:
            for c in self._credo_connection:
                self.credo.disconnect(c)
        finally:
            self._credo_connection = []

    def rowCount(self, parent: QtCore.QModelIndex = None):
        if not isinstance(parent, QtCore.QModelIndex):
            parent = QtCore.QModelIndex()
        if not parent.isValid():
            # we are the root index
            return len(self.credo.config)
        else:
            obj = self._get_object(parent)
            if isinstance(obj, dict):
                return len(obj)
            else:
                return 0

    def columnCount(self, parent: QtCore.QModelIndex = None):
        return 1

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.DisplayRole:
            return self._get_path(index)[-1]
        elif role == QtCore.Qt.EditRole:
            return self._get_object(index)
        else:
            return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role==QtCore.Qt.DisplayRole:
            return 'Key'
        else:
            return None

    def _get_path(self, index:QtCore.QModelIndex):
        if not index.isValid():
            return []
        else:
            return index.internalPointer().split(':')

    def _get_object(self, index:QtCore.QModelIndex):
        if not index.isValid():
            return self.credo.config
        dic = self.credo.config
        path = index.internalPointer().split(':')
        for p in path:
            dic=dic[p]
        return dic

    def parent(self, child: QtCore.QModelIndex):
        if not child.isValid():
            return QtCore.QModelIndex()
        path = child.internalPointer().split(':')
        if not path:
            return QtCore.QModelIndex()
        elif not path[:-1]:
            return QtCore.QModelIndex()
        else:
            dic = self.credo.config
            for p in path[:-1]:
                dic=dic[p]
            row = sorted(list(dic.keys())).index(path[-1])
            return self.createIndex(row, 0, path[:-1])

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = None):
        if not isinstance(parent, QtCore.QModelIndex):
            parent = QtCore.QModelIndex()
        if not parent.isValid():
            path=[sorted(list(self.credo.config.keys()))[row]]
            return self.createIndex(row, column, path)
        else:
            parentpath = parent.internalPointer().split(':')
            dic = self.credo.config
            for p in parentpath:
                dic = dic[p]
            path=parentpath+[sorted(list(dic.keys()))[row]]
            return self.createIndex(row, column, path)

    def createIndex(self, row: int, column: int, object: typing.Any = ...):
        path = ':'.join([s for s in object])
        if path in self._indices:
            return self._indices[path]
        else:
            self._indices[path] = super().createIndex(row, column, path)
            return self._indices[path]

    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = ...):
        if role in [QtCore.Qt.EditRole, QtCore.Qt.DisplayRole]:
            dic=self.credo.config
            path = self._get_path(index)
            for p in path[:-1]:
                dic = dic[p]
            dic[path[-1]] = value
            self.credo.save_state()
            return True
        else:
            return False

    def flags(self, index: QtCore.QModelIndex):
        obj = self._get_object(index)
        if isinstance(obj, dict):
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        elif isinstance(obj, (float, int, str, bool)):
            return QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren

    def getValue(self, index:QtCore.QModelIndex):
        return self._get_object(index)

    def getPath(self, index:QtCore.QModelIndex):
        return self._get_path(index)

    def getIndexForPath(self, path) -> QtCore.QModelIndex:
        if not path:
            # the root index
            return QtCore.QModelIndex()
        else:
            # first level entry
            obj = self._get_object(self.getIndexForPath(path[:-1]))
            row = sorted(list(obj.keys())).index(path[0])
            return self.index(row, 0, QtCore.QModelIndex())
