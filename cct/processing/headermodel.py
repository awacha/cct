import datetime
import gc
import os
import queue
import threading
from typing import List, Any, Union, Iterable

import numpy as np
from PyQt5 import QtCore
from sastool.io.credo_cct import Header
from sastool.misc.errorvalue import ErrorValue

from ..core.utils.timeout import IdleFunction


class HeaderModel(QtCore.QAbstractItemModel):

    fsnloaded = QtCore.pyqtSignal(int, int, int)

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
        #self.reloadHeaders()
        
    def config(self):
        return self._parent.config

    def cache_pathes(self):
        for attrname, subdirname in [('eval2d_pathes', 'eval2d'),
                                     ('mask_pathes', 'mask')]:
            setattr(self, attrname, [os.path.join(
                self.rootdir, self.config()['path']['directories'][subdirname])])
            with os.scandir(getattr(self, attrname)[0]) as it:
                for entry in it:
                    if entry.is_dir():
                        getattr(self, attrname).append(entry.path)


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

    def is_badfsn(self, fsn:Union[int, Iterable[int]]) -> Union[bool, List[bool]]:
        if isinstance(fsn, int):
            return fsn in self.get_badfsns()
        bfs=self.get_badfsns()
        return [f in bfs for f in fsn]

    def write_badfsns(self, badfsns:List[int]):
        folder, file= os.path.split(self.badfsnsfile)
        os.makedirs(folder, exist_ok=True)
        np.savetxt(self.badfsnsfile, badfsns)

    def reloadHeaders(self):
        self.queue=queue.Queue()
        self.reloaderworker=threading.Thread(None, loadHeaderDataWorker, args=(
            self.queue, self.config()['path']['prefixes']['crd'],
            self.config()['path']['fsndigits'],
            self.eval2d_pathes, self.fsnfirst, self.fsnlast, self.visiblecolumns))
        self._fsns_loaded=0
        self.reloaderworker.start()
        self._idlefcn = IdleFunction(self.checkReloaderWorker,100)

    def checkReloaderWorker(self):
        for i in range(10):
            try:
                fsn=self.queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(fsn, int):
                print('FSN: {}'.format(fsn))
                self._fsns_loaded+=1
                self.fsnloaded.emit(self.fsnlast-self.fsnfirst+1, self._fsns_loaded, fsn)
            else:
                print('DONE!!!')
                self.beginResetModel()
                self._headers, self._fsns = fsn
                self._badstatus = self.is_badfsn(self._fsns)
                self.endResetModel()
                self.fsnloaded.emit(0,0,0)
                self.reloaderworker.join()
                del self.queue
                del self.reloaderworker
                del self._fsns_loaded
                self._idlefcn.stop()
                del self._idlefcn
                return False
        return True

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

def load_header(fsn, prefix, fsndigits, path):
#    prefix = self.config()['path']['prefixes']['crd']
    for p in path:
        try:
            fn=os.path.join(p,'{{}}_{{:0{:d}d}}.pickle'.format(fsndigits).format(prefix, fsn))
            h=Header.new_from_file(fn)
            return h
        except FileNotFoundError:
            continue
    raise FileNotFoundError(fsn)

def loadHeaderDataWorker(queue, prefix, fsndigits, path, fsnfirst, fsnlast, columns):
    _headers=[]
    _fsns=[]
    for fsn in range(fsnfirst, fsnlast + 1):
        try:
            h = load_header(fsn, prefix, fsndigits, path)
            hd=[]
            for c in columns:
                try:
                    hd.append(getattr(h, c))
                except (KeyError, AttributeError):
                    hd.append('N/A')
            _headers.append(hd)
            _fsns.append(fsn)
            for i, x in enumerate(_headers[-1]):
                if isinstance(x, ErrorValue):
                    _headers[-1][i] = x.val
                elif x is None:
                    _headers[-1][i] = '--'
                elif isinstance(x, datetime.datetime):
                    _headers[-1][i] = str(x)
            queue.put_nowait(fsn)
            del h
        except FileNotFoundError:
            pass
    queue.put_nowait((_headers, _fsns))
    return None