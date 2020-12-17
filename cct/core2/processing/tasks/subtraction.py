import enum
import multiprocessing
import queue
from typing import List, Any, Optional, Sequence, Tuple
import logging

from PyQt5 import QtCore

from .task import ProcessingTask, ProcessingStatus, ProcessingSettings
from ..calculations.backgroundprocess import Message
from ..calculations.subtractionjob import SubtractionScalingMode, SubtractionJob, SubtractionResult

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SubtractionData:
    samplename: Optional[str]
    distancekey: Optional[str] = None
    backgroundname: Optional[str] = None
    scalingmode: SubtractionScalingMode
    statusmessage: str = '--'
    spinner: Optional[int] = None
    progresstotal: int = 0
    progresscurrent: int = 0
    errormessage: Optional[str] = None
    traceback: Optional[str] = None
    factor: Tuple[float, float]
    interval: Tuple[float, float, int]

    def __init__(self, samplename: Optional[str], background: Optional[str], scalingmode: SubtractionScalingMode, factor: Tuple[float, float], interval: Tuple[float, float, int]):
        self.samplename = samplename
        self.backgroundname = background
        self.factor = factor
        self.interval = interval
        self.scalingmode = scalingmode

    def isRunning(self) -> bool:
        return self.spinner is not None

    @property
    def subtractedname(self) -> str:
        return f'{self.samplename}-{self.backgroundname}'

class Subtraction(ProcessingTask):
    _data: List[SubtractionData] = None

    def __init__(self, processing: "Processing", settings: ProcessingSettings):
        self._data = []
        super().__init__(processing, settings)
        self.reload()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 4

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        sd = self._data[index.row()]
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return sd.samplename if sd.samplename is not None else '-- None --'
            elif index.column() == 1:
                return sd.backgroundname if sd.backgroundname is not None else '-- None --'
            elif index.column() == 2:
                return sd.scalingmode.value
            elif index.column() == 3:
                if sd.scalingmode == SubtractionScalingMode.Unscaled:
                    return None
                elif sd.scalingmode == SubtractionScalingMode.Constant:
                    return f'{sd.factor[0]:.4f}\xb1{sd.factor[1]:.4f}'
                elif sd.scalingmode in [SubtractionScalingMode.Interval, SubtractionScalingMode.PowerLaw]:
                    return f'{sd.interval[0]:.4f} ≤ q ≤ {sd.interval[1]:.4f} ({sd.interval[2]} pts)'
                else:
                    assert False
        elif role == QtCore.Qt.EditRole:
            if index.column() == 0:
                return sd.samplename
            elif index.column() == 1:
                return sd.backgroundname
            elif index.column() == 2:
                return sd.scalingmode
            elif index.column() == 3:
                if sd.scalingmode == SubtractionScalingMode.Unscaled:
                    return None
                elif sd.scalingmode == SubtractionScalingMode.Constant:
                    return sd.factor
                elif sd.scalingmode in [SubtractionScalingMode.Interval, SubtractionScalingMode.PowerLaw]:
                    return sd.interval
                else:
                    assert False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Sample', 'Background', 'Scaling method', 'Parameters'][section]

    def addSubtractionPair(self, samplename: Optional[str], background: Optional[str], mode: SubtractionScalingMode = SubtractionScalingMode.Unscaled, factor: Optional[Tuple[float, float]]=None, interval:Optional[Tuple[float, float, int]]=None):
        self.beginInsertRows(QtCore.QModelIndex(), len(self._data), len(self._data))
        self._data.append(SubtractionData(samplename, background, mode, factor if factor is not None else (1.0, 0.0), interval if interval is not None else (0.0, 1000.0, 100)))
        self.endInsertRows()
        self.save()

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        if parent is ...:
            parent = QtCore.QModelIndex()
        self.beginRemoveRows(parent, row, row)
        del self._data[row]
        self.endRemoveRows()
        self.save()

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        if parent is ...:
            parent = QtCore.QModelIndex()
        self.beginRemoveRows(parent, row, row+count-1)
        del self._data[row:row+count]
        self.endRemoveRows()
        self.save()

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        if parent is ...:
            parent = QtCore.QModelIndex()
        self.beginInsertRows(parent, row, row)
        self._data=self._data[:row] + [SubtractionData(None, None, SubtractionScalingMode.Unscaled, (),)] + self._data[row:]
        self.endInsertRows()
        self.save()

    def insertRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        if parent is ...:
            parent = QtCore.QModelIndex()
        self.beginInsertRows(parent, row, row+count-1)
        self._data = self._data[:row] + [
            SubtractionData(None, None, SubtractionScalingMode.Unscaled, (), ) for i in range(count)] + self._data[row:]
        self.endInsertRows()
        self.save()

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        sd = self._data[index.row()]
        if index.column() == 0:
            # change sample name
            sd.samplename = value
        elif index.column() == 1:
            sd.backgroundname = value
        elif index.column() == 2:
            sd.scalingmode = SubtractionScalingMode(value)
        elif index.column() == 3:
            if sd.scalingmode == SubtractionScalingMode.Unscaled:
                pass
            elif sd.scalingmode == SubtractionScalingMode.Constant:
                assert isinstance(value, tuple) and isinstance(value[0], float) and isinstance(value[1], float) and (len(value) == 2)
                sd.factor = value
            elif sd.scalingmode in [SubtractionScalingMode.Interval, SubtractionScalingMode.PowerLaw]:
                assert isinstance(value, tuple) and isinstance(value[0], float) and isinstance(value[1], float) and isinstance(value[2], int) and (len(value) == 3)
                sd.interval = value
            else:
                assert False
        else:
            return False
        self.dataChanged.emit(self.index(index.row(), 0, QtCore.QModelIndex()),
                              self.index(index.row(), self.columnCount(), QtCore.QModelIndex()))
        self.save()

    def reload(self):
        self.beginResetModel()
        self._data = []
        with self.settings.h5io.reader('Samples') as grp:
            for sname in sorted(grp):
                if 'subtraction_samplename' not in grp[sname].attrs:
                    continue
                self._data.append(
                    SubtractionData(
                        grp[sname].attrs['subtraction_samplename'],
                        grp[sname].attrs['subtraction_background'],
                        SubtractionScalingMode(grp[sname].attrs['subtraction_mode']),
                        (grp[sname].attrs['subtraction_factor'],
                         grp[sname].attrs['subtraction_factor_unc']),
                        (grp[sname].attrs['subtraction_qmin'],
                         grp[sname].attrs['subtraction_qmax'],
                         grp[sname].attrs['subtraction_qcount'])))
        self.endResetModel()

    def save(self):
        with self.settings.h5io.writer('Samples') as grp:
            # first remove all subtracted samples
            for sample in grp:
                if 'sample_category' in grp[sample].attrs:
                    # if the sample group already has information on the 'subtractedness'
                    if (grp[sample].attrs['sample_category'] == 'subtracted') and (sample not in [sd.subtractedname for sd in self._data]):
                        del grp[sample]
                else:
                    # see the distance subgroups
                    for distkey in grp[sample]:
                        if ('sample_category' in grp[sample][distkey].attrs) and (grp[sample][distkey].attrs['sample_category'] == 'subtracted') and (sample not in [sd.subtractedname for sd in self._data]):
                            del grp[sample]
                            break
            for sd in self._data:
                g = grp.require_group(sd.subtractedname)
                g.attrs['subtraction_samplename'] = sd.samplename if sd.samplename is not None else '-- None --'
                g.attrs['subtraction_background'] = sd.backgroundname if sd.backgroundname is not None else '-- None --'
                g.attrs['subtraction_mode'] = sd.scalingmode.value
                g.attrs['subtraction_factor'] = sd.factor[0]
                g.attrs['subtraction_factor_unc'] = sd.factor[1]
                g.attrs['subtraction_qmin'] = sd.interval[0]
                g.attrs['subtraction_qmax'] = sd.interval[1]
                g.attrs['subtraction_qcount'] = sd.interval[2]
                g.attrs['sample_category'] = 'subtracted'

    def _start(self):
        for i, sd in enumerate(self._data):
            self._submitTask(SubtractionJob.run, jobid=i, samplename=sd.samplename, backgroundname=sd.backgroundname,
                             scalingmode=sd.scalingmode, interval=sd.interval, factor=sd.factor,
                             subtractedname=sd.subtractedname)

    def onBackgroundTaskFinished(self, result: SubtractionResult):
        self._data[result.jobid].spinner = None

    def onAllBackgroundTasksFinished(self):
        pass

    def onBackgroundTaskError(self, jobid: Any, errormessage: str, traceback: str):
        pass