import copy
import datetime
import logging
import pickle
import traceback
from typing import List, Any, Optional, Union, Iterable, Final, Tuple

from PyQt5 import QtCore, QtGui

from ..component import Component
from ..motors import Motor
from ....dataclasses.descriptors import LockState
from ....dataclasses.sample import Sample

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SampleStore(QtCore.QAbstractItemModel, Component):
    _samples: List[Sample]
    _currentsample: Optional[str]
    _columns: Final[List[Tuple[str, str]]] = [
        ('title', 'Title'),
        ('positionx', 'X position'),
        ('positiony', 'Y position'),
        ('distminus', 'Dist. decr.'),
        ('thickness', 'Thickness (cm)'),
        ('transmission', 'Transmission'),
        ('preparedby', 'Prepared by'),
        ('preparetime', 'Preparation date'),
        ('category', 'Category'),
        ('situation', 'Situation')]

    _movesampledirection: str = 'both'
    sampleListChanged = QtCore.pyqtSignal()
    currentSampleChanged = QtCore.pyqtSignal(str)
    movingToSample = QtCore.pyqtSignal(str, str, float, float,
                                       float)  # sample, motor name, motor position, start position, end position
    movingFinished = QtCore.pyqtSignal(bool, str)  # success, sample

    def __init__(self, **kwargs):
        self._samples = []
        super().__init__(**kwargs)
        self._currentsample = None
        # self.loadFromConfig()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        logger.debug(f'rowCount: {len(self._samples)}')
        return len(self._samples)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        if not parent.isValid():
            return len(self._columns)
        else:
            return 0

    def beginRemoveRows(self, parent: QtCore.QModelIndex, first: int, last: int) -> None:
        logger.debug(f'beginRemoveRows({parent=}, {first=}, {last=}')
        return super(SampleStore, self).beginRemoveRows(parent, first, last)
    
    def beginInsertRows(self, parent: QtCore.QModelIndex, first: int, last: int) -> None:
        logger.debug(f'beginInsertRows({parent=}, {first=}, {last=}')
        return super(SampleStore, self).beginInsertRows(parent, first, last)

    def endRemoveRows(self) -> None:
        logger.debug('endRemoveRows')
        return super(SampleStore, self).endRemoveRows()
    
    def endInsertRows(self) -> None:
        logger.debug('endInsertRows')
        return super(SampleStore, self).endInsertRows()

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._columns[section][1]

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        parameter = self._columns[index.column()][0]
        try:
            sample = self._samples[index.row()]
        except IndexError:
            logger.error('++++\n'.join([line.strip() for line in traceback.format_stack()]))
            logger.warning(f'{index.row()=}, {index.column()=}, {index.isValid()=}, {index.parent().isValid()=} {len(self._samples)=}')
            raise
            return QtCore.Qt.ItemNeverHasChildren
        if sample.isLocked(parameter):
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | \
                   QtCore.Qt.ItemIsDragEnabled
        else:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemNeverHasChildren | \
                   QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDragEnabled

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if index.row() >= len(self._samples):
            logger.warning(f'in data(): {index.row()} > {len(self._samples)}')
        if role == QtCore.Qt.UserRole:
            return self._samples[index.row()]
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
            self.dataChanged.emit(self.index(index.row(), index.column(), QtCore.QModelIndex()),
                                  self.index(index.row(), index.column(), QtCore.QModelIndex()))
        self.saveToConfig()
        return True

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
#        if parent.isValid():
#            return QtCore.QModelIndex()
        return self.createIndex(row, column, None)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def mimeData(self, indexes: Iterable[QtCore.QModelIndex]) -> QtCore.QMimeData:
        logger.debug('mimeData')
        md = QtCore.QMimeData()
        samples = [self._samples[i.row()] for i in indexes]
        md.setData('application/x-cctsamplelist', pickle.dumps(samples))
        return md

    def mimeTypes(self) -> List[str]:
        logger.debug('MimeTypes')
        return ['application/x-cctsamplelist']

    def supportedDragActions(self) -> QtCore.Qt.DropAction:
        logger.debug('supportedDragActions')
        return QtCore.Qt.CopyAction

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
        self.beginResetModel()
        self._samples.insert(row, Sample(title))
        self.endResetModel()
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
        self.beginResetModel()
        cpy = copy.copy(self[title])
        cpy.title = LockState.UNLOCKED
        cpy.title = dupname
        self._samples.insert(row, cpy)
        self.endResetModel()
        self.sampleListChanged.emit()
        self.saveToConfig()
        return dupname

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        logger.debug(f'Removing row {row}. Number of rows: {self.rowCount(QtCore.QModelIndex())}')
        self.beginResetModel()
        logger.debug('Deleting sample')
        del self._samples[row]
        logger.debug('Ending remove rows')
        self.endResetModel()
        logger.debug('Ended remove rows')
        return True

    def removeSample(self, title: str):
        logger.debug(f'Removing sample {title=}')
        idx = self._samples.index(self[title])
        logger.debug(f'Sample index is {idx}')
        if self._samples[idx].isLocked('title'):
            raise ValueError('Cannot delete protected sample.')
        if title == self._currentsample:
            raise ValueError('Cannot delete current sample')
        self.removeRow(idx, QtCore.QModelIndex())
        logger.debug(f'Removed sample.')
        logger.debug('Saving to config')
        self.saveToConfig()
        logger.debug('Emitting samplelistchanged')
        self.sampleListChanged.emit()
        logger.debug('End.')

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
            self.saveToConfig()
        else:
            raise ValueError(f'Unknown sample "{title}"')

    def updateSample(self, title: str, sample: Sample):
        logger.debug(f'Updating sample {title} with sample {sample.title}')
        row = [i for i, s in enumerate(self._samples) if s.title == title][0]
        if sample.title != title:
            self.removeRow(row, QtCore.QModelIndex())
            row = max([i for i, s in enumerate(self._samples) if s.title.upper() < sample.title.upper()] + [-1]) + 1
            logger.debug(f'Inserting row {row=}')
            self.beginInsertRows(QtCore.QModelIndex(), row, row)
            self._samples.insert(row, copy.copy(sample))
            self.endInsertRows()
            logger.debug(f'Inserted row {row=}')
        else:
            self._samples[row] = sample
        logger.debug('Emitting datachanged')
        self.dataChanged.emit(self.index(row, 0, QtCore.QModelIndex()),
                              self.index(row, self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))
        logger.debug('Emitting sampleListChanged')
        self.sampleListChanged.emit()
        logger.debug('Saving to config')
        self.saveToConfig()

    def findSample(self, title: str) -> QtCore.QModelIndex:
        row = [i for i, s in enumerate(self._samples) if s.title == title][0]
        logger.debug(f'findsample({title=}): {row=}')
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
        self.setCurrentSample(samplename)
        self._connectSampleMotors()
        self._movesampledirection = direction
        try:
            if direction in ['both', 'x']:
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

    def onMotorMoving(self, current: float, start: float, end: float):
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
