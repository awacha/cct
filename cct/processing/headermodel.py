import datetime
import gc
import os

from PyQt5 import QtCore
from sastool.io.credo_cct import Header
from sastool.misc.errorvalue import ErrorValue


class HeaderModel(QtCore.QAbstractItemModel):

    def __init__(self, parent, rootdir, prefix, fsnfirst, fsnlast, visiblecolumns):
        super().__init__(None)
        self.prefix = prefix
        self.fsnfirst = fsnfirst
        self.fsnlast = fsnlast
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
                for i, x in enumerate(self._headers[-1]):
                    if isinstance(x, ErrorValue):
                        self._headers[-1][i] = x.val
                    elif x is None:
                        self._headers[-1][i] = '--'
                    elif isinstance(x, datetime.datetime):
                        self._headers[-1][i] = str(x)
                del h
            except FileNotFoundError:
                print('Not found header: {}'.format(fsn))
        self.endResetModel()

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._headers)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.visiblecolumns)

    def index(self, row, column, parent=None, *args, **kwargs):
        return self.createIndex(row, column, None)

    def parent(self, index: QtCore.QModelIndex = None):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role=None):
        if role == QtCore.Qt.DisplayRole:
            return self._headers[index.row()][index.column()]
        if role == QtCore.Qt.CheckStateRole and index.column()==0:
            #ToDo: enable and disable headers
            return None
        return None

    def headerData(self, column, orientation, role=None):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.visiblecolumns[column].capitalize()
        return None

    def cleanup(self):
        self.beginResetModel()
        del self._headers
        self._headers=[]
        self.endResetModel()
        gc.collect()