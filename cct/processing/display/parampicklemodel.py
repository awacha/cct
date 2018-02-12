from PyQt5 import QtCore
from typing import Dict, List, Optional, Any
import numpy as np
from sastool import ErrorValue
import datetime

class ParamPickleModel(QtCore.QAbstractItemModel):
    def __init__(self, parent):
        super().__init__(parent)
        self._indexlists = []
        self._paramdict = {}

    def setParamPickle(self, param:Dict):
        self.beginResetModel()
        self._indexlists = []
        self._paramdict = param
        self.endResetModel()

    def _getDict(self, path:Optional[List[str]]):
        if path is None:
            return self._paramdict
        dic = self._paramdict
        for p in path:
            dic = dic[p]
        return dic

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        dic = self._getDict(parent.internalPointer())
        if isinstance(dic, (dict, list)):
            return len(dic)
        else:
            return 0

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        dic = self._getDict(parent.internalPointer())
        if isinstance(dic, (dict, list)):
            return 2
        else:
            return 0

    def parent(self, child: QtCore.QModelIndex):
        if not child.internalPointer():
            return QtCore.QModelIndex()
        return self.createIndex(child.row(), child.column(), child.internalPointer()[:-1])

    def createIndex(self, row: int, column: int, object: Any = ...):
        try:
            idxlist = [x for x in self._indexlists if x == object][0]
        except IndexError:
            self._indexlists.append(object)
            idxlist = object
        return super().createIndex(row, column, idxlist)

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        ip = parent.internalPointer()
        if ip is None:
            ip = []
        dic = self._getDict(ip)
        if isinstance(dic, dict):
            key = sorted(dic.keys())[row]
        elif isinstance(dic, list):
            key = row
        else:
            raise TypeError(dic)
        return self.createIndex(row, column, ip+[key])

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        if role == QtCore.Qt.DisplayRole:
            dic = self._getDict(index.internalPointer())
            if index.column()==0:
                return index.internalPointer()[-1]
            elif index.column()==1 and isinstance(
                    dic,
                    (str, int, float,
                     np.number, ErrorValue,
                     datetime.datetime, datetime.date, datetime.time, type(None))):
                return str(dic)
            else:
                return str(type(dic))
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return ['Key', 'Value'][section]
        return None

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable



