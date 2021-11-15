import copy
import logging
import pickle
from typing import List, Any, Optional, Union, Iterable, Final, Tuple

from PyQt5 import QtCore, QtGui

from ..component import Component
from ..motors import Motor
from ....dataclasses.sample import Sample, LockState

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
    currentSampleChanged = QtCore.pyqtSignal(object)  # sample name or None
    sampleEdited = QtCore.pyqtSignal(str, str, object)
    movingToSample = QtCore.pyqtSignal(str, str, float, float,
                                       float)  # sample, motor name, motor position, start position, end position
    movingFinished = QtCore.pyqtSignal(bool, str)  # success, sample

    def __init__(self, **kwargs):
        self._samples = []
        super().__init__(**kwargs)
        self._currentsample = None
        # self.loadFromConfig()

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._samples)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._columns)

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        attribute = self._columns[index.column()][0]
        sample = self._samples[index.row()]
        if ((role == QtCore.Qt.DisplayRole) or (role == QtCore.Qt.EditRole)) and (attribute == 'title'):
            return sample.title
        elif ((role == QtCore.Qt.DisplayRole) or (role == QtCore.Qt.EditRole)) and (attribute == 'preparedby'):
            return sample.preparedby
        elif ((role == QtCore.Qt.DisplayRole) or (role == QtCore.Qt.EditRole)) and (attribute == 'category'):
            return sample.category.value
        elif ((role == QtCore.Qt.DisplayRole) or (role == QtCore.Qt.EditRole)) and (attribute == 'situation'):
            return sample.situation.value
        elif (role == QtCore.Qt.DisplayRole) and (attribute == 'preparetime'):
            return str(sample.preparetime)
        elif (role == QtCore.Qt.EditRole) and (attribute == 'preparetime'):
            return sample.preparetime
        elif (role == QtCore.Qt.DisplayRole) and (attribute == 'positionx'):
            return f'{sample.positionx[0]:.4f}'
        elif (role == QtCore.Qt.DisplayRole) and (attribute == 'positiony'):
            return f'{sample.positiony[0]:.4f}'
        elif (role == QtCore.Qt.DisplayRole) and (attribute == 'thickness'):
            return f'{sample.thickness[0]:.4f}'
        elif (role == QtCore.Qt.DisplayRole) and (attribute == 'distminus'):
            return f'{sample.distminus[0]:.4f}'
        elif (role == QtCore.Qt.DisplayRole) and (attribute == 'transmission'):
            return f'{sample.transmission[0]:.4f}'
        elif (role == QtCore.Qt.EditRole) and (
                attribute in ['positionx', 'positiony', 'thickness', 'distminus', 'transmission']):
            return getattr(sample, attribute)
        elif role == QtCore.Qt.DecorationRole:
            return QtGui.QIcon.fromTheme('lock') if sample.isLocked(attribute) else None
        elif (role == QtCore.Qt.ToolTipRole) and (attribute == 'title'):
            return sample.description
        elif (role == QtCore.Qt.ToolTipRole) and (
                attribute in ['positionx', 'positiony', 'thickness', 'distminus', 'transmission']):
            attr = getattr(sample, attribute)
            return f'{attr[0]:.4f} \xb1 {attr[1]:.4f}'
        else:
            return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        sample = self._samples[index.row()]
        attribute = self._columns[index.column()][0]
        if role == QtCore.Qt.EditRole:
            try:
                return self.updateSample(sample.title, attribute, value)
            except Exception:
                return False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        sample = self._samples[index.row()]
        attr = self._columns[index.column()][0]
        if sample.isLocked(attr):
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsDragEnabled | \
                   QtCore.Qt.ItemIsEnabled  # note that if it is not enabled, we cannot select it!
        else:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsDragEnabled | \
                   QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled

    def sort(self, column: int, order: QtCore.Qt.SortOrder = ...) -> None:
        attr = self._columns[column][0]
        self.beginResetModel()
        try:
            if attr in ['title', 'description', 'preparedby', 'preparetime', 'category', 'situation']:
                self._samples = list(sorted(self._samples, key=lambda s: getattr(s, attr)))
            elif attr in ['positionx', 'thickness', 'positiony', 'transmission', 'distminus']:
                self._samples = list(sorted(self._samples, key=lambda s: getattr(s, attr)[0]))
            else:
                raise ValueError(f'Unknown attribute {attr}')
        finally:
            self.endResetModel()

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        if parent is ...:
            parent = QtCore.QModelIndex()
        assert not parent.isValid()
        self.beginRemoveRows(parent, row, row)
        try:
            del self._samples[row]
            return True
        except ValueError:
            return False
        finally:
            self.endRemoveRows()
            self.sampleListChanged.emit()
            self.saveToConfig()

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        if parent is ...:
            parent = QtCore.QModelIndex()
        assert not parent.isValid()
        self.beginRemoveRows(parent, row, row + count - 1)
        try:
            for i in range(count):
                del self._samples[row]
            return True
        except ValueError:
            return False
        finally:
            self.endRemoveRows()
            self.sampleListChanged.emit()
            self.saveToConfig()

    def insertRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        if parent is ...:
            parent = QtCore.QModelIndex()
        assert not parent.isValid()
        self.beginInsertRows(parent, row, row + count - 1)
        for i in range(count):
            self._samples.insert(row + i, Sample(self.getFreeSampleName('Untitled')))
        self.endInsertRows()
        self.sampleListChanged.emit()
        self.saveToConfig()
        return True

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        if parent is ...:
            parent = QtCore.QModelIndex()
        assert not parent.isValid()
        logger.debug(f'Inserting a sample at {row=}')
        self.beginInsertRows(parent, row, row)
        logger.debug(f'Doing the insertion itself. {len(self._samples)=}')
        self._samples.insert(row, Sample(self.getFreeSampleName('Untitled')))
        logger.debug(f'End of insertrows. {len(self._samples)=}')
        self.endInsertRows()
        logger.debug('Emitting sampleListChanged')
        self.sampleListChanged.emit()
        logger.debug('Done.')
        self.saveToConfig()
        return True

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return self._columns[section][1]

    def mimeData(self, indexes: Iterable[QtCore.QModelIndex]) -> QtCore.QMimeData:
        md = QtCore.QMimeData()
        samples = [self._samples[i.row()] for i in indexes]
        md.setData('application/x-cctsamplelist', pickle.dumps(samples))
        return md

    def mimeTypes(self) -> List[str]:
        return ['application/x-cctsamplelist']

    def supportedDragActions(self) -> QtCore.Qt.DropAction:
        return QtCore.Qt.CopyAction

    def __contains__(self, item: str) -> bool:
        return item in [s.title for s in self._samples]

    def __iter__(self) -> Iterable[Sample]:
        yield from self._samples

    def __getitem__(self, item: Union[str, int]) -> Sample:
        return copy.deepcopy([s for i, s in enumerate(self._samples) if (s.title == item) or (i == item)][0])

    def __len__(self) -> int:
        return len(self._samples)

    def updateAttributeLocking(self, samplename: str, attribute: str, locked: bool):
        sample = [s for s in self._samples if s.title == samplename][0]
        setattr(sample, attribute, LockState.LOCKED if locked else LockState.UNLOCKED)
        row = self._samples.index(sample)
        try:
            column = [i for i, (attr, label) in enumerate(self._columns) if attr == attribute][0]
            self.dataChanged.emit(self.index(row, column, QtCore.QModelIndex()),
                                  self.index(row, column, QtCore.QModelIndex()))
        except IndexError:
            pass
        self.sampleEdited.emit(sample.title, attribute, getattr(sample, attribute))
        self.saveToConfig()

    def updateSample(self, samplename: str, attribute: str, value: Any) -> bool:
        sample = [s for s in self._samples if s.title == samplename][0]
        if getattr(sample, attribute) == value:
            # no need to change.
            return False
        # at this point, the new value is guaranteed to be different from the present one
        if attribute == 'title':
            # handle this differently
            if value in self:
                raise ValueError(
                    f'Cannot rename sample {sample.title} to {value}: another sample with this title already exists.')
        setattr(sample, attribute, value)
        row = self._samples.index(sample)
        try:
            column = [i for i, (attr, label) in enumerate(self._columns) if attr == attribute][0]
            self.dataChanged.emit(self.index(row, column, QtCore.QModelIndex()),
                                  self.index(row, column, QtCore.QModelIndex()))
        except IndexError:
            pass
        self.saveToConfig()
        self.sampleEdited.emit(sample.title, attribute, getattr(sample, attribute))
        return True

    def getFreeSampleName(self, prefix: str) -> str:
        if prefix not in self:
            return prefix
        i = 0
        while (sn := f'{prefix}_{i}') in self:
            i += 1
        return sn

    def addSample(self, samplename: Optional[str] = None, sample: Optional[Sample] = None) -> str:
        logger.debug('Adding a sample')
        if (samplename is not None) and (samplename in self):
            raise ValueError(f'Cannot add sample: another sample with this name ({samplename}) already exists.')
        logger.debug('Calling insertRow')
        if not self.insertRow(self.rowCount()):
            raise ValueError('Cannot add sample')
        if sample is not None:
            logger.debug('Modifying the recently added sample')
            self._samples[-1] = copy.deepcopy(sample)
            self.dataChanged.emit(self.index(len(self._samples) - 1, 0, QtCore.QModelIndex()),
                                  self.index(len(self._samples) - 1, len(self._columns) - 1, QtCore.QModelIndex()))
        if samplename is not None:
            logger.debug('Modifying the name of the recently added sample')
            self._samples[-1].title = samplename
            self.dataChanged.emit(self.index(len(self._samples) - 1, 0, QtCore.QModelIndex()),
                                  self.index(len(self._samples) - 1, 0, QtCore.QModelIndex()))
        logger.debug('Emitting sample list changed')
        self.sampleListChanged.emit()
        self.saveToConfig()
        return self._samples[-1].title

    def indexForSample(self, samplename: str) -> QtCore.QModelIndex:
        row = [i for i, s in enumerate(self._samples) if s.title == samplename][0]
        return self.index(row, 0, QtCore.QModelIndex())

    def loadFromConfig(self):
        self.beginResetModel()
        self._samples = []
        for sample in self.config['services']['samplestore']['list']:
            self._samples.append(Sample.fromdict(self.config['services']['samplestore']['list'][sample].asdict()))
        if ('active' in self.config['services']['samplestore']) and (
                self.config['services']['samplestore']['active'] in self):
            self.setCurrentSample(self.config['services']['samplestore']['active'])
        else:
            self.setCurrentSample(None)
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

    def setCurrentSample(self, title: Optional[str]):
        if title is None:
            self._currentsample = None
            self.currentSampleChanged.emit(None)
        elif title in self:
            self._currentsample = title
            self.currentSampleChanged.emit(title)
            self.saveToConfig()
        else:
            raise ValueError(f'Unknown sample "{title}"')

    def currentSample(self) -> Optional[Sample]:
        if self._currentsample is None:
            return None
        return self[self._currentsample]

    def hasMotors(self) -> bool:
        try:
            self.xmotor()
            self.ymotor()
        except KeyError:
            return False
        else:
            return True

    def xmotor(self) -> Motor:
        return self.instrument.motors.sample_x

    def ymotor(self) -> Motor:
        return self.instrument.motors.sample_y

    def xmotorname(self) -> str:
        return self.instrument.motors.sample_x.name

    def ymotorname(self) -> str:
        return self.instrument.motors.sample_y.name

    def moveToSample(self, samplename: str, direction='both'):
        try:
            xmotor = self.xmotor()
            ymotor = self.ymotor()
        except KeyError as ke:
            # motor not found
            raise
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
            return
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
