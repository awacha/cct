import copy
import datetime
import logging
import pickle
from typing import List, Any, Optional, Union, Iterable

from PyQt5 import QtCore, QtGui

from ....dataclasses.descriptors import LockState
from ....dataclasses.sample import Sample
from ..component import Component
from ..motors import Motor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SampleStore(QtCore.QAbstractItemModel, Component):
    _samples: List[Sample]
    _currentsample: Optional[str]
    singleColumnMode: bool = True
    _columns = [('title', 'Title'),
                ('positionx', 'X position'),
                ('positiony', 'Y position'),
                ('distminus', 'Dist. decr.'),
                ('thickness', 'Thickness (cm)'),
                ('transmission', 'Transmission'),
                ('preparedby', 'Prepared by'),
                ('preparetime', 'Preparation date'),
                ('category', 'Category'),
                ('situation', 'Situation')]

    _movesampledirection: str='both'
    sampleListChanged = QtCore.pyqtSignal()
    currentSampleChanged = QtCore.pyqtSignal(str)
    movingToSample = QtCore.pyqtSignal(str, str, float, float, float)  # sample, motor name, motor position, start position, end position
    movingFinished = QtCore.pyqtSignal(bool, str)  # success, sample

    def __init__(self, **kwargs):
        self._samples = []
        super().__init__(**kwargs)
        self._currentsample = None
        #self.loadFromConfig()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._samples)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 1 if self.singleColumnMode else 10

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._columns[section][1]

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        parameter = self._columns[index.column()][0]
        if self._samples[index.row()].isLocked(parameter):
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | \
                   QtCore.Qt.ItemIsDragEnabled
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | \
                   QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDragEnabled

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if role == QtCore.Qt.UserRole:
            return self._samples[index.row()]
        if self.singleColumnMode:
            if role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
                return self._samples[index.row()].title
            if role == QtCore.Qt.ToolTipRole:
                return self._samples[index.row()].description
        elif role == QtCore.Qt.ToolTipRole:
            return self._samples[index.row()].description
        elif role in [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole]:
            sample = self._samples[index.row()]
            if index.column() == 0:  # title
                return sample.title
            elif index.column() == 1:  # x position
                return f'{sample.positionx[0]:.4f}' if role == QtCore.Qt.DisplayRole else sample.positionx[0]
            elif index.column() == 2:  # y position
                return f'{sample.positiony[0]:.4f}' if role == QtCore.Qt.DisplayRole else sample.positiony[0]
            elif index.column() == 3:  # distminus
                return f'{sample.distminus[0]:.4f}' if role == QtCore.Qt.DisplayRole else sample.distminus[0]
            elif index.column() == 4:  # thickness
                return f'{sample.thickness[0]:.4f}' if role == QtCore.Qt.DisplayRole else sample.thickness[0]
            elif index.column() == 5:  # transmission
                return f'{sample.transmission[0]:.4f}' if role == QtCore.Qt.DisplayRole else sample.transmission[0]
            elif index.column() == 6:  # pereparedby
                return sample.preparedby
            elif index.column() == 7:  # preparetime
                return f'{sample.preparetime}' if role == QtCore.Qt.DisplayRole else QtCore.QDate(
                    sample.preparetime.year, sample.preparetime.month, sample.preparetime.day)
            elif index.column() == 8:  # category
                return sample.category.value
            elif index.column() == 9:  # situation
                return sample.situation.value
        elif role in [QtCore.Qt.DecorationRole]:
            sample = self._samples[index.row()]
            attr = self._columns[index.column()][0]
            return QtGui.QIcon.fromTheme('lock') if sample.isLocked(attr) else None
        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        attribute = self._columns[index.column()][0]
        sample = self[index.row()]
        if attribute == 'title':
            if value in self:
                # this title already exists: either it is the sample to be changed (in this case no change needed) or
                # another sample (in this case the change must not be done).
                return False
            oldtitle = sample.title
            sample.title = value
            self.updateSample(oldtitle, sample)
        else:
            if isinstance(value, QtCore.QDate):
                value = datetime.date(value.year(), value.month(), value.day())
            setattr(self._samples[index.row()], attribute, value)
            self.dataChanged.emit(index, index)
        self.saveToConfig()
        return True

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def mimeData(self, indexes: Iterable[QtCore.QModelIndex]) -> QtCore.QMimeData:
        md = QtCore.QMimeData()
        samples = [self._samples[i.row()] for i in indexes]
        md.setData('application/x-cctsamplelist', pickle.dumps(samples))
        return md

    def mimeTypes(self) -> List[str]:
        return ['application/x-cctsamplelist']

    def supportedDragActions(self) -> QtCore.Qt.DropAction:
        return QtCore.Qt.CopyAction


    def setSingleColumnMode(self, singlecolumnmode: bool = True):
        self.beginResetModel()
        self.singleColumnMode = singlecolumnmode
        self.endResetModel()

    def loadFromConfig(self):
        self.beginResetModel()
        self._samples = []
        for sample in self.config['services']['samplestore']['list']:
            self._samples.append(Sample.fromdict(self.config['services']['samplestore']['list'][sample].asdict()))
        self._samples = sorted(self._samples, key=lambda s: s.title.upper())
        self.endResetModel()

    def saveToConfig(self):
        self.config.blockSignals(True)
        if 'samplestore' not in self.config['services']:
            self.config['services']['samplestore'] = {}
        if 'list' not in self.config['services']['samplestore']:
            self.config['services']['samplestore']['list'] = {}
        for sample in self._samples:
            self.config['services']['samplestore']['list'][sample.title] = sample.todict()
        sampletitles = [s.title for s in self._samples]
        removedsamples = [k for k in self.config['services']['samplestore']['list'] if k not in sampletitles]
        for sn in removedsamples:
            del self.config['services']['samplestore']['list'][sn]
        self.config.blockSignals(False)
        self.config.changed.emit(('services', 'samplestore', 'list'), self.config['services']['samplestore']['list'])

    def addSample(self, title: Optional[str] = None):
        if title is None:
            i = 0
            while f'Untitled_{i}' in self:
                i += 1
            title = f'Untitled_{i}'
        if title in self:
            raise ValueError('Sample name already exists.')
        comesbefore = [i for (i, sam) in enumerate(self._samples) if sam.title.upper() < title.upper()]
        row = max(comesbefore + [-1]) + 1
        self.beginInsertRows(QtCore.QModelIndex(), row, row + 1)
        self._samples.insert(row, Sample(title))
        self.endInsertRows()
        self.sampleListChanged.emit()
        self.saveToConfig()
        return title

    def duplicateSample(self, title: str, dupname: Optional[str] = None):
        if title not in self:
            raise ValueError(f'Sample "{title}" does not exist.')
        if dupname is None:
            i = 0
            while f'{title}_copy{i}' in self:
                i += 1
            dupname = f'{title}_copy{i}'
        assert isinstance(dupname, str)
        if dupname in self:
            raise ValueError('Sample name already exists.')
        logger.warning(dupname)
        comesbefore = [i for (i, sam) in enumerate(self._samples) if sam.title.upper() < dupname.upper()]
        row = max(comesbefore + [-1]) + 1
        self.beginInsertRows(QtCore.QModelIndex(), row, row + 1)
        cpy = copy.copy(self[title])
        cpy.title = LockState.UNLOCKED
        cpy.title = dupname
        self._samples.insert(row, cpy)
        self.endInsertRows()
        self.sampleListChanged.emit()
        self.saveToConfig()
        return dupname

    def removeSample(self, title: str):
        idx = self._samples.index(self[title])
        if self._samples[idx].isLocked('title'):
            raise ValueError('Cannot delete protected sample.')
        self.beginRemoveRows(QtCore.QModelIndex(), idx, idx)
        del self._samples[idx]
        self.endRemoveRows()
        if title == self._currentsample:
            self._currentsample = None
            self.currentSampleChanged.emit(None)
        self.sampleListChanged.emit()
        self.saveToConfig()

    def __contains__(self, item: Union[str, Sample]) -> bool:
        if isinstance(item, str):
            return item in [s.title for s in self._samples]
        elif isinstance(item, Sample):
            return item in self._samples
        else:
            raise TypeError('Invalid type')

    def __getitem__(self, item: Union[str, int]) -> Sample:
        if isinstance(item, str):
            try:
                return copy.copy([s for s in self._samples if s.title == item][0])
            except IndexError:
                raise KeyError(item)
        else:
            return copy.copy(self._samples[item])

    def setCurrentSample(self, title: str):
        if title in self:
            self._currentsample = title
            self.currentSampleChanged.emit(title)
        else:
            raise ValueError(f'Unknown sample "{title}"')

    def updateSample(self, title: str, sample: Sample):
        logger.debug(f'Updating sample {title} with sample {sample.title}')
        row = [i for i, s in enumerate(self._samples) if s.title == title][0]
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._samples[row]
        self.endRemoveRows()
        row = max([i for i, s in enumerate(self._samples) if s.title.upper() < sample.title.upper()] + [-1]) + 1
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._samples.insert(row, copy.copy(sample))
        self.endInsertRows()
        self.dataChanged.emit(self.index(row, 0, QtCore.QModelIndex()),
                              self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))
        self.sampleListChanged.emit()
        self.saveToConfig()

    def findSample(self, title: str) -> QtCore.QModelIndex:
        row = [i for i, s in enumerate(self._samples) if s.title == title][0]
        return self.index(row, 0, QtCore.QModelIndex())

    def __iter__(self) -> Iterable[Sample]:
        for sample in self._samples:
            yield sample

    def xmotor(self) -> Motor:
        return self.instrument.motors.sample_x

    def ymotor(self) -> Motor:
        return self.instrument.motors.sample_y

    def xmotorname(self) -> str:
        return self.instrument.motors.sample_x.name

    def ymotorname(self) -> str:
        return self.instrument.motors.sample_y.name

    def currentSample(self) -> Optional[Sample]:
        if self._currentsample is None:
            return None
        return self[self._currentsample]

    def moveToSample(self, samplename: str, direction='both'):
        logger.debug(f'Moving to sample {samplename}')
        if self.xmotor().isMoving() or self.ymotor().isMoving():
            raise RuntimeError('Cannot move sample: motors are not idle.')
        sample = [s for s in self._samples if s.title == samplename][0]
        self._currentsample = samplename
        self._connectSampleMotors()
        self._movesampledirection = direction
        try:
            if direction in  ['both', 'x']:
                self.xmotor().moveTo(sample.positionx[0])
            else:
                self.ymotor().moveTo(sample.positiony[0])
        except Exception as exc:
            logger.error(f'Cannot start move to sample: {str(exc)}')
            self._disconnectSampleMotors()
            self.movingFinished.emit(False, self._currentsample)

    def _connectSampleMotors(self):
        for motor in [self.xmotor(), self.ymotor()]:
            motor.started.connect(self.onMotorStarted)
            motor.stopped.connect(self.onMotorStopped)
            motor.moving.connect(self.onMotorMoving)

    def _disconnectSampleMotors(self):
        for motor in [self.xmotor(), self.ymotor()]:
            motor.started.disconnect(self.onMotorStarted)
            motor.stopped.disconnect(self.onMotorStopped)
            motor.moving.disconnect(self.onMotorMoving)

    def onMotorMoving(self, current:float, start:float, end:float):
        self.movingToSample.emit(self._currentsample, self.sender().name, current, start, end)

    def onMotorStarted(self, start: float):
        pass

    def onMotorStopped(self, success: bool, end: float):
        logger.debug(f'Motor {self.sender().name} stopped. Success: {success}. End: {end:.4f}')
        if not success:
            self._disconnectSampleMotors()
            self.movingFinished.emit(False, self._currentsample)
        if (self.sender() is self.xmotor()) and (self._movesampledirection == 'both'):
            try:
                self.ymotor().moveTo(self.currentSample().positiony[0])
            except Exception:
                self._disconnectSampleMotors()
                self.movingFinished.emit(False, self._currentsample)
                raise
        elif (self.sender() is self.ymotor()) or (self._movesampledirection == 'x'):
            self._disconnectSampleMotors()
            self.movingFinished.emit(True, self._currentsample)
        else:
            assert False

    def stopMotors(self):
        self.xmotor().stop()
        self.ymotor().stop()