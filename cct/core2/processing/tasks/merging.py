from typing import Dict, List, Any, Optional
import logging

from .task import ProcessingTask
from ..settings import ProcessingSettings
from ..calculations.mergingjob import MergingResult, MergingJob
from collections import namedtuple
from PyQt5 import QtCore, QtGui
import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MergeParameters=namedtuple('MergeParameters', ['qmin', 'qmax'])


class MergingData:
    samplename: str
    intervals: Dict[str, MergeParameters]
    statusmessage: str = '--'
    spinner: Optional[int] = None
    errormessage: Optional[str] = None
    traceback: Optional[str] = None

    def __init__(self, samplename: Optional[str]):
        self.samplename = samplename
        self.intervals = {}
        self.statusmessage = '--'
        self.spinner = None

    def __len__(self):
        return len(self.intervals)


class Merging(ProcessingTask):
    _data: List[MergingData]
    spinnerTimer: Optional[QtCore.QTimer]
    
    def __init__(self, processing: "Processing", settings:ProcessingSettings):
        self._data=[]
        super().__init__(processing, settings)
        self.reload()
        
    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        if not parent.isValid():
            # 1st level item: sample name
            return len(self._data)
        elif not parent.parent().isValid():
            # 2nd level item: distance key
            return len(self._data[parent.row()])
        else:
            return 0
    
    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 3
#        if not parent.isValid():
#            # 1st level item: sample name
#            return 1
#        elif not parent.parent().isValid():
#            # 2nd level item: distance key
#            return 3
#        else:
#            return 0

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not child.isValid():
            raise ValueError('Invalid child index')
        elif child.internalPointer() is None:
            return QtCore.QModelIndex()
        elif isinstance(child.internalPointer(), MergingData):
            return self.index(self._data.index(child.internalPointer()), 0, QtCore.QModelIndex())
        else:
            raise ValueError('Invalid child index #2')

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if not index.isValid():
            # root item
            return
        elif not index.parent().isValid():
            # 1st level index: sample name and nothing else
            md = self._data[index.row()]
            if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
                return md.samplename
            elif (index.column() == 3) and (role == QtCore.Qt.DisplayRole):
                return md.statusmessage if md.errormessage is None else md.errormessage
            elif (role == QtCore.Qt.BackgroundColorRole) and (md.errormessage is not None):
                return QtGui.QColor('red').lighter(50)
            elif (role == QtCore.Qt.TextColorRole) and (md.errormessage is not None):
                return QtGui.QColor('black')
            elif (index.column() == 0) and (role == QtCore.Qt.DecorationRole):
                return QtGui.QIcon(QtGui.QPixmap(f':/icons/spinner_{md.spinner % 12:02d}.svg')) if md.spinner is not None else None
            elif (role == QtCore.Qt.ToolTipRole) and (md.errormessage is not None):
                return md.traceback

        elif not index.parent().parent().isValid():
            # 2nd level index: distance key
            md = self._data[index.parent().row()]
            distkey = list(sorted(md.intervals.keys(), key=lambda k:float(k)))[index.row()]
            if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
                return distkey
            elif (index.column() == 1) and (role == QtCore.Qt.DisplayRole):
                return f'{md.intervals[distkey].qmin:.4f}'
            elif (index.column() == 2) and (role == QtCore.Qt.DisplayRole):
                return f'{md.intervals[distkey].qmax:.4f}'
            elif (index.column() == 1) and (role == QtCore.Qt.EditRole):
                return md.intervals[distkey].qmin
            elif (index.column() == 2) and (role == QtCore.Qt.EditRole):
                return md.intervals[distkey].qmax

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        if not parent.isValid():
            # 1st level item
            return self.createIndex(row, column, None)
        elif parent.internalPointer() is None:
            # 2nd level item
            md = self._data[parent.row()]
            return self.createIndex(row, column, md)
        else:
            raise ValueError('Invalid index requested')

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if not index.isValid():
            # root index
            return QtCore.Qt.ItemIsEnabled
        elif not index.parent().isValid():
            # 1st level index: sample name. No columns are editable
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        elif index.column() == 0:
            # 2nd level index: distance & qmin & qmax: qmin and qmax are editable, the distance label not.
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        else:
            # 2nd level index: qmin & qmax editable
            assert index.column() in [1,2]
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if not index.parent().isValid():
            raise ValueError('Top-level items are not editable')
        md = self._data[index.parent().row()]
        distkey = sorted(md.intervals.keys(), key=lambda k:float(k))[index.row()]
        qmin, qmax = md.intervals[distkey]
        if index.column() == 1:
            md.intervals[distkey] = MergeParameters(float(value), qmax)
        elif index.column() == 2:
            md.intervals[distkey] = MergeParameters(qmin, float(value))
        else:
            return False
        self.dataChanged.emit(self.index(index.row(), 0, index.parent()), self.index(index.row(), self.columnCount(index.parent()), index.parent()))
        self.save()
        return True
    
    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Sample/Distance', 'qmin', 'qmax', 'status'][section]

    def addSample(self, samplename: str):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._data), len(self._data))
        self._data.append(MergingData(samplename))
        for distkey in self.processing.settings.h5io.distancekeys(samplename):
            exposure = self.processing.settings.h5io.readExposure(f'Samples/{samplename}/{distkey}')
            q = exposure.q()[0][exposure.mask.astype(np.bool)]
            self._data[-1].intervals[distkey] = MergeParameters(np.nanmin(q), np.nanmax(q))
        self.endInsertRows()
        self.save()

    def removeSample(self, samplename: str):
        row = [i for i, md in enumerate(self._data) if md.samplename == samplename][0]
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._data[row]
        self.endRemoveRows()

    def __contains__(self, item: str) -> bool:
        return bool([md for md in self._data if md.samplename == item])

    def _start(self):
        for i, md in enumerate(self._data):
            md.errormessage = None
            md.statusmessage = 'Queued...'
            md.traceback = None
            md.spinner = 0
            self._submitTask(MergingJob.run, i, samplename=md.samplename, distancekeys=sorted(md.intervals.keys()), intervals=[md.intervals[k] for k in sorted(md.intervals)])
        self.dataChanged.emit(
            self.index(0, 0, QtCore.QModelIndex()),
            self.index(
                self.rowCount(QtCore.QModelIndex()),
                self.columnCount(QtCore.QModelIndex()),
                QtCore.QModelIndex()))
        self.spinnerTimer = QtCore.QTimer()
        self.spinnerTimer.setTimerType(QtCore.Qt.PreciseTimer)
        self.spinnerTimer.timeout.connect(self.onSpinnerTimerTimeout)
        self.spinnerTimer.start(200)

    def onBackgroundTaskProgress(self, jobid: Any, total: int, current: int, message: str):
        self._data[jobid].statusmessage=message
        self.dataChanged.emit(self.index(jobid, 0, QtCore.QModelIndex()),
                              self.index(jobid, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def onBackgroundTaskFinished(self, result: MergingResult):
        self._data[result.jobid].spinner = None
        self.dataChanged.emit(self.index(result.jobid, 0, QtCore.QModelIndex()),
                              self.index(result.jobid, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))

    def onAllBackgroundTasksFinished(self):
        for md in self._data:
            md.spinner = None

    def onBackgroundTaskError(self, jobid: Any, errormessage: str, traceback: str):
        self._data[jobid].errormessage = errormessage
        self._data[jobid].traceback = traceback

    def onSpinnerTimerTimeout(self):
        for md in self._data:
            if md.spinner is not None:
                md.spinner += 1
        self.dataChanged.emit(self.index(0,0, QtCore.QModelIndex()),
                              self.index(self.rowCount(QtCore.QModelIndex()), 0, QtCore.QModelIndex()))
        if all([md.spinner is None for md in self._data]):
            self.spinnerTimer.stop()
            self.spinnerTimer.deleteLater()
            self.spinnerTimer = None

    def save(self):
        with self.settings.h5io.writer('Samples') as grp:
            for md in self._data:
                grp.require_group(md.samplename)
                mg=grp[md.samplename].require_group('merged')
                scgrp = mg.require_group('scaled_curves')
                for name in scgrp:
                    if name not in md.intervals:
                        del scgrp[name]
                for distkey in sorted(md.intervals, key=lambda k: float(k)):
                    dkgroup = scgrp.require_group(distkey)
                    dkgroup.attrs['qmin'] = md.intervals[distkey].qmin
                    dkgroup.attrs['qmax'] = md.intervals[distkey].qmax

    def reload(self):
        self.beginResetModel()
        with self.settings.h5io.reader('Samples') as grp:
            for samplename in sorted(grp):
                if 'merged' not in grp[samplename]:
                    continue
                if 'scaled_curves' not in grp[samplename]['merged']:
                    continue
                md = MergingData(samplename)
                md.intervals = {
                    distkey:MergeParameters(
                        grp[f'{samplename}/merged/scaled_curves/{distkey}'].attrs['qmin'],
                        grp[f'{samplename}/merged/scaled_curves/{distkey}'].attrs['qmax'],
                    ) for distkey in grp[f'{samplename}/merged/scaled_curves']
                }
                self._data.append(md)
        self.endResetModel()
