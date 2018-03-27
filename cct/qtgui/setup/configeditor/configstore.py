import typing
from typing import List, Any, Union
import logging

from PyQt5 import QtCore

from ....core.instrument.instrument import Instrument

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ConfigStore(QtCore.QAbstractItemModel):
    def __init__(self, credo: Instrument):
        super().__init__(None)
        self.credo = credo
        self._paths = {}
        self._credo_connection = []
        self.destroyed.connect(self.onDestroyed)
        self.credo.connect('config-changed', self.onConfigChanged)

    def onConfigChanged(self, credo: Instrument):
        self.beginResetModel()
        self._paths = {}
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
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return 'Key'
        else:
            return None

    def _get_path(self, index: QtCore.QModelIndex):
        if not index.isValid():
            return []
        else:
            return index.internalPointer().split(':')

    def _get_object(self, pathorindex: Union[List[str],QtCore.QModelIndex]):
        dic = self.credo.config
        if isinstance(pathorindex, QtCore.QModelIndex):
            if not pathorindex.isValid():
                pathorindex = []
            else:
                pathorindex = self._get_path(pathorindex)
        elif pathorindex is None:
            pathorindex = []
        for p in pathorindex:
            dic = dic[p]
        return dic

    def parent(self, child: QtCore.QModelIndex):
        path = self._get_path(child)
        if len(path)<=1:
            # child is either on the first level -> parent should be an invalid index, or is an invalid index itself
            return QtCore.QModelIndex()
        parentofparentobj = self._get_object(path[:-1])
        rowindexofparent = sorted(list(parentofparentobj.keys())).index(path[-1])
        return self.createIndex(rowindexofparent, 0, path[:-1])

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = None):
        if not isinstance(parent, QtCore.QModelIndex):
            # a safety measure: None parent means an invalid parent
            parent = QtCore.QModelIndex()
        if not parent.isValid():
            # if the parent is invalid: we are on the root level
            path = [sorted(list(self.credo.config.keys()))[row]]
            return self.createIndex(row, column, path)
        parentpath = self._get_path(parent)
        parentobject = self._get_object(parentpath)
        path = parentpath + [sorted(list(parentobject.keys()))[row]]
        return self.createIndex(row, column, path)

    def createIndex(self, row: int, column: int, object: typing.Any = ...):
        path = ':'.join([s for s in object])
        if path not in self._paths:
            self._paths[path] = super().createIndex(row, column, path)
        return self._paths[path]
    def setData(self, index: QtCore.QModelIndex, value: typing.Any, role: int = ...):
        if role in [QtCore.Qt.EditRole, QtCore.Qt.DisplayRole]:
            path = self._get_path(index)
            parentobj = self._get_object(self.parent(index))
            parentobj[path[-1]] = value
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

    def getValue(self, index: QtCore.QModelIndex):
        return self._get_object(index)

    def getPath(self, index: QtCore.QModelIndex):
        return self._get_path(index)

    def getIndexForPath(self, path) -> QtCore.QModelIndex:
        if not path:
            # the root index
            return QtCore.QModelIndex()
        else:
            # we must have a parent object
            parentobj = self._get_object(path[:-1])
            row = int(sorted(list(parentobj.keys())).index(path[-1]))
            return self.index(row, 0, self.getIndexForPath(path[:-1]))
