import datetime
import gc
import os
from typing import List, Any

import numpy as np
from PyQt5 import QtCore
from sastool.io.credo_cct import Header
from sastool.misc.errorvalue import ErrorValue


class HeaderModel(QtCore.QAbstractItemModel):

    def __init__(self, parent, rootdir, prefix, fsnfirst, fsnlast, visiblecolumns, badfsnsfile):
        super().__init__(None)
        self.prefix = prefix
        self.fsnfirst = fsnfirst
        self.fsnlast = fsnlast
        self.badfsnsfile=badfsnsfile
        self._badstatus=[]
        self._fsns=[]
        # the columns you want to display. Note that the first MUST be always 'fsn' or the code will break. Sorry!
        if not visiblecolumns:
            visiblecolumns=['fsn', 'title', 'distance', 'date', 'temperature']
        self.visiblecolumns=visiblecolumns
        self._headers = []
        self._parent=parent
        self.rootdir=rootdir
        self.eval2d_pathes=[]
        self.mask_pathes=[]
        self.cache_pathes()
        self.reloadHeaders()
        
    def config(self):
        return self._parent.config

    def cache_pathes(self):
        prefix = self.config()['path']['prefixes']['crd']
        for attrname, subdirname in [('eval2d_pathes', 'eval2d'),
                                     ('mask_pathes', 'mask')]:
            setattr(self, attrname, [os.path.join(
                self.rootdir, self.config()['path']['directories'][subdirname])])
            with os.scandir(getattr(self, attrname)[0]) as it:
                for entry in it:
                    if entry.is_dir():
                        getattr(self, attrname).append(entry.path)

    def load_header(self, fsn):
        prefix = self.config()['path']['prefixes']['crd']
        for p in self.eval2d_pathes:
            try:
                fn=os.path.join(p,'{{}}_{{:0{:d}d}}.pickle'.format(self.config()['path']['fsndigits']).format(prefix, fsn))
                h=Header.new_from_file(os.path.join(p,'{{}}_{{:0{:d}d}}.pickle'.format(self.config()['path']['fsndigits']).format(prefix, fsn)))
                return h
            except FileNotFoundError:
                continue
        raise FileNotFoundError(fsn)

    def rowForFSN(self, fsn: int):
        colidx = self.visiblecolumns.index('fsn') # can raise IndexError
        return [h[colidx] for h in self._headers].index(fsn)

    def get_badfsns(self):
        try:
            data=np.loadtxt(self.badfsnsfile).tolist()
            if not isinstance(data,list):
                data=[data]
            return [int(d) for d in data]
        except FileNotFoundError:
            return []

    def is_badfsn(self, fsn:int) -> bool:
        return fsn in self.get_badfsns()

    def write_badfsns(self, badfsns:List[int]):
        folder, file= os.path.split(self.badfsnsfile)
        os.makedirs(folder, exist_ok=True)
        np.savetxt(self.badfsnsfile, badfsns)

    def reloadHeaders(self):
        self.beginResetModel()
        self._headers = []
        for fsn in range(self.fsnfirst, self.fsnlast + 1):
            try:
                h = self.load_header(fsn)
                hd=[]
                for c in self.visiblecolumns:
                    try:
                        hd.append(getattr(h, c))
                    except KeyError:
                        hd.append('N/A')
                self._headers.append(hd)
                self._badstatus.append(self.is_badfsn(fsn))
                self._fsns.append(fsn)
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
        self.endResetModel()

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._headers)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.visiblecolumns)+1

    def index(self, row, column, parent=None, *args, **kwargs):
        return self.createIndex(row, column, None)

    def parent(self, index: QtCore.QModelIndex = None):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        flags = QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable

        if index.column()==0:
            flags |= QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled
        elif not self._badstatus[index.row()]:
            flags |= QtCore.Qt.ItemIsEnabled
        return flags

    def data(self, index: QtCore.QModelIndex, role=None):
        if role == QtCore.Qt.DisplayRole:
            if index.column()==0:
                return ['OK','BAD'][self._badstatus[index.row()]]
            else:
                return self._headers[index.row()][index.column()-1]
        if role == QtCore.Qt.CheckStateRole and index.column()==0:
            return (QtCore.Qt.Unchecked, QtCore.Qt.Checked)[self._badstatus[index.row()]]
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...):
        if role==QtCore.Qt.CheckStateRole and index.column()==0:
            self._badstatus[index.row()]=bool(value)
            self.dataChanged.emit(self.index(index.row(), 0),self.index(index.row(),self.columnCount()),[QtCore.Qt.CheckStateRole, QtCore.Qt.DisplayRole])
            self.write_badfsns([f for f,bs in zip(self._fsns, self._badstatus) if bs])
            return True
        return False

    def headerData(self, column, orientation, role=None):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return (['Bad?']+self.visiblecolumns)[column].capitalize()
        return None

    def update_badfsns(self, badfsns):
        for i,f in enumerate(self._fsns):
            if f in badfsns:
                self._badstatus[i]=True
                self.dataChanged.emit(self.index(i,0),self.index(i,self.columnCount()),[QtCore.Qt.DisplayRole, QtCore.Qt.CheckStateRole])
        self.write_badfsns([f for f,bs in zip(self._fsns, self._badstatus) if bs])

    def cleanup(self):
        self.beginResetModel()
        del self._headers
        self._headers=[]
        self.endResetModel()
        gc.collect()

    def sort(self, column: int, order: QtCore.Qt.SortOrder = ...):
        data = zip(self._fsns, self._badstatus, self._headers)
        if column>0:
            sorteddata = sorted(data, key=lambda x:x[2][column-1], reverse=order==QtCore.Qt.DescendingOrder)
        else:
            sorteddata = sorted(data, key=lambda x:x[1], reverse=order==QtCore.Qt.DescendingOrder)
        self.beginResetModel()
        self._fsns = [f[0] for f in sorteddata]
        self._badstatus = [f[1] for f in sorteddata]
        self._headers = [f[2] for f in sorteddata]
        self.endResetModel()
        pass