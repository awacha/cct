import datetime
import gc
import os
import queue
import threading
from typing import List, Any, Union, Iterable, Set

import numpy as np
from PyQt5 import QtCore
from sastool.io.credo_cct import Header as Header_cct
from sastool.io.credo_saxsctrl import Header as Header_saxsctrl
from sastool.misc.errorvalue import ErrorValue

from ....core.utils.timeout import IdleFunction


class HeaderModel(QtCore.QAbstractItemModel):
    visiblecolumns = ['fsn', 'title', 'distance', 'date', 'temperature']

    fsnloaded = QtCore.pyqtSignal(int, int, int)

    def __init__(self, parent, rootdir, prefix, fsnranges, visiblecolumns, badfsnsfile):
        super().__init__(None)
        self.prefix = prefix
        self.fsnranges = fsnranges
        self.badfsnsfile = badfsnsfile
        self._data = []  # fsn, title, distance, isbad, date, exptime, (visible parameters)
        # the columns you want to display
        if not visiblecolumns:
            visiblecolumns = ['fsn', 'title', 'distance', 'date', 'temperature']
        self.visiblecolumns = visiblecolumns
        self._parent = parent
        self.rootdir = rootdir
        self.eval2d_pathes = []
        self.mask_pathes = []
        self.cache_pathes()
        # self.reloadHeaders()

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        return (self.prefix == other.prefix) and (self.badfsnsfile == other.badfsnsfile) and (
                    self.rootdir == other.rootdir)

    def setBadFSNFile(self, badfsnsfile):
        self.beginResetModel()
        self.badfsnsfile = badfsnsfile
        self.endResetModel()

    def config(self):
        return self._parent.cctConfig

    def cache_pathes(self):
        for attrname, subdirname in [('eval2d_pathes', 'eval2d'),
                                     ('mask_pathes', 'mask')]:
            setattr(self, attrname, [os.path.join(
                self.rootdir, self.config()['path']['directories'][subdirname])])
            with os.scandir(getattr(self, attrname)[0]) as it:
                for entry in it:
                    if entry.is_dir():
                        getattr(self, attrname).append(entry.path)

    def rowForFSN(self, fsn: int) -> int:
        return [h[0] for h in self._data].index(fsn)

    def get_badfsns(self) -> List[int]:
        try:
            f = np.loadtxt(self.badfsnsfile).flatten().astype(int).tolist()
            if not isinstance(f, list):
                f = list(f)
            return list(set(f))
        except (FileNotFoundError, OSError):
            return []

    def is_badfsn(self, fsn: Union[int, Iterable[int]]) -> Union[bool, List[bool]]:
        if isinstance(fsn, int):
            return fsn in self.get_badfsns()
        bfs = self.get_badfsns()
        return [f in bfs for f in fsn]

    def fsn_is_in_range(self, fsn):
        for left, right in self.fsnranges:
            if fsn>=left and fsn<=right:
                return True
        return False

    def goodfsns(self):
        lis = []
        badfsns = self.get_badfsns()
        for left, right in self.fsnranges:
            lis.extend([x for x in range(left, right+1) if x not in badfsns])
        return lis

    def write_badfsns(self, badfsns: List[int]):
        badfsns_to_save = [b for b in self.get_badfsns() if
                           self.fsn_is_in_range(b)]  # do not touch fsns outside our range
        badfsns_to_save.extend(badfsns)
        folder, file = os.path.split(self.badfsnsfile)
        os.makedirs(folder, exist_ok=True)
        np.savetxt(self.badfsnsfile, badfsns_to_save, fmt='%.0f')

    def reloadHeaders(self):
        self.queue = queue.Queue()
        self.reloaderworker = threading.Thread(None, loadHeaderDataWorker, args=(
            self.queue, self.config()['path']['prefixes']['crd'],
            self.config()['path']['fsndigits'],
            self.eval2d_pathes, self.fsnranges, self.visiblecolumns))
        self._fsns_loaded = 0
        self.reloaderworker.start()
        self._idlefcn = IdleFunction(self.checkReloaderWorker, 100)

    def checkReloaderWorker(self):
        for i in range(10):
            try:
                fsn = self.queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(fsn, int):
                self._fsns_loaded += 1
                numfsns=sum([right-left+1 for right, left in self.fsnranges])
                self.fsnloaded.emit(numfsns, self._fsns_loaded, fsn)
            else:
                self.beginResetModel()
                fsns, titles, distances, exptimes, dates, visiblecolumndata = fsn
                self._data = list(
                    zip(fsns, titles, distances, self.is_badfsn(fsns), dates, exptimes, visiblecolumndata))
                self.endResetModel()
                self.fsnloaded.emit(0, 0, 0)
                self.reloaderworker.join()
                del self.queue
                del self.reloaderworker
                del self._fsns_loaded
                self._idlefcn.stop()
                del self._idlefcn
                return False
        return True

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self._data)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.visiblecolumns) + 1

    def index(self, row, column, parent=None, *args, **kwargs):
        return self.createIndex(row, column, None)

    def parent(self, index: QtCore.QModelIndex = None):
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex):
        flags = QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable

        if index.column() == 0:
            flags |= QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled
        elif not self._data[index.row()][3]:
            flags |= QtCore.Qt.ItemIsEnabled
        return flags

    def data(self, index: QtCore.QModelIndex, role=None):
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return ['OK', 'BAD'][self._data[index.row()][3]]
            else:
                return self._data[index.row()][-1][index.column() - 1]
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            return (QtCore.Qt.Unchecked, QtCore.Qt.Checked)[self._data[index.row()][3]]
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...):
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            originaldata = self._data[index.row()]
            self._data[index.row()] = originaldata[:3] + (bool(value),) + originaldata[4:]
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount()),
                                  [QtCore.Qt.CheckStateRole, QtCore.Qt.DisplayRole])
            self.write_badfsns([d[0] for d in self._data if d[3]])
            return True
        return False

    def headerData(self, column, orientation, role=None):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return (['Bad?'] + self.visiblecolumns)[column].capitalize()
        return None

# fsn, title, distance, isbad, date, exptime, (visible parameters)
    def update_badfsns(self, badfsns):
        for i, d in enumerate(self._data):
            if d[0] in badfsns:
                self._data[i] = d[:3] + (True,) + d[4:]
                self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount()),
                                      [QtCore.Qt.DisplayRole, QtCore.Qt.CheckStateRole])
        self.write_badfsns([d[0] for d in self._data if d[3]])

    def cleanup(self):
        self.beginResetModel()
        del self._data
        self._data = []
        self.endResetModel()
        gc.collect()

    def sort(self, column: int, order: QtCore.Qt.SortOrder = ...):
        sorteddata = sorted(self._data, key=lambda x: x[-1][column - 1], reverse=order == QtCore.Qt.DescendingOrder)
        self.beginResetModel()
        self._data = sorteddata
        self.endResetModel()

    def getFSN(self, index: QtCore.QModelIndex):
        return self._data[index.row()][0]

    def sampleNames(self) -> Set[str]:
        return {d[1] for d in self._data}

    def netExposureTime(self):
        return float(sum([d[5] for d in self._data]))

    def netGoodExposureTime(self):
        return float(sum([d[5] for d in self._data if not d[3]]))

    def netBadExposureTime(self):
        return float(sum([d[5] for d in self._data if d[3]]))

    def countGoodExposures(self):
        return len([d for d in self._data if not d[3]])

    def countBadExposures(self):
        return len([d for d in self._data if d[3]])

    def totalExperimentTime(self):
        mintime = min([d[4] for d in self._data])
        maxtime = max([d[4] for d in self._data])
        return (maxtime - mintime).total_seconds()


def load_header(fsn, prefix, fsndigits, path):
    #    prefix = self.config()['path']['prefixes']['crd']
    for p in path:
        for extn, cls in [('.pickle', Header_cct),
                          ('.pickle.gz',Header_cct),
                          ('.param',Header_saxsctrl),
                          ('.param.gz',Header_saxsctrl)]:
            try:
                fn = os.path.join(p, '{{}}_{{:0{:d}d}}{}'.format(fsndigits, extn).format(prefix, fsn))
                h = cls.new_from_file(fn)
                return h
            except FileNotFoundError:
                continue
    raise FileNotFoundError(fsn)


def loadHeaderDataWorker(queue, prefix, fsndigits, path, fsnranges, columns):
    _headers = []
    _fsns = []
    _titles = []
    _distances = []
    _exptimes = []
    _dates = []
    fsns = []
    for left, right in fsnranges:
        fsns.extend(list(range(left, right+1)))
    for fsn in fsns:
        try:
            h = load_header(fsn, prefix, fsndigits, path)
            hd = []
            for c in columns:
                try:
                    hd.append(getattr(h, c))
                except (KeyError, AttributeError):
                    hd.append('N/A')
            _headers.append(hd)
            _fsns.append(fsn)
            _titles.append(h.title)
            _exptimes.append(h.exposuretime)
            _dates.append(h.date)
            _distances.append(h.distance)
            # some type adjustments...
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
            continue
    queue.put_nowait((_fsns, _titles, _distances, _exptimes, _dates, _headers))
    return None
