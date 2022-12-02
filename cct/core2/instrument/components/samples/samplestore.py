import copy
import logging
import pickle
from typing import List, Any, Optional, Union, Iterable, Final, Tuple

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Signal, Slot

from ..component import Component
from ..motors import Motor
from ....dataclasses.sample import Sample, LockState

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SampleStore(Component, QtCore.QAbstractItemModel):
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
    sampleListChanged = Signal()
    currentSampleChanged = Signal(object)  # sample name or None
    sampleEdited = Signal(str, str, object)
    movingToSample = Signal(str, str, float, float,
                                       float)  # sample, motor name, motor position, start position, end position
    movingFinished = Signal(bool, str)  # success, sample
    sortedmodel: QtCore.QSortFilterProxyModel

    def __init__(self, **kwargs):
        self._samples = []
        super().__init__(**kwargs)
        self._currentsample = None
        self.sortedmodel = QtCore.QSortFilterProxyModel()
        self.sortedmodel.setSourceModel(self)
        self.sortedmodel.sort(0, QtCore.Qt.SortOrder.AscendingOrder)
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
        if ((role == QtCore.Qt.ItemDataRole.DisplayRole) or (role == QtCore.Qt.ItemDataRole.EditRole)) and (attribute == 'title'):
            return sample.title
        elif ((role == QtCore.Qt.ItemDataRole.DisplayRole) or (role == QtCore.Qt.ItemDataRole.EditRole)) and (attribute == 'preparedby'):
            return sample.preparedby
        elif ((role == QtCore.Qt.ItemDataRole.DisplayRole) or (role == QtCore.Qt.ItemDataRole.EditRole)) and (attribute == 'category'):
            return sample.category.value
        elif ((role == QtCore.Qt.ItemDataRole.DisplayRole) or (role == QtCore.Qt.ItemDataRole.EditRole)) and (attribute == 'situation'):
            return sample.situation.value
        elif (role == QtCore.Qt.ItemDataRole.DisplayRole) and (attribute == 'preparetime'):
            return str(sample.preparetime)
        elif (role == QtCore.Qt.ItemDataRole.EditRole) and (attribute == 'preparetime'):
            return sample.preparetime
        elif (role == QtCore.Qt.ItemDataRole.DisplayRole) and (attribute == 'positionx'):
            return f'{sample.positionx[0]:.4f}'
        elif (role == QtCore.Qt.ItemDataRole.DisplayRole) and (attribute == 'positiony'):
            return f'{sample.positiony[0]:.4f}'
        elif (role == QtCore.Qt.ItemDataRole.DisplayRole) and (attribute == 'thickness'):
            return f'{sample.thickness[0]:.4f}'
        elif (role == QtCore.Qt.ItemDataRole.DisplayRole) and (attribute == 'distminus'):
            return f'{sample.distminus[0]:.4f}'
        elif (role == QtCore.Qt.ItemDataRole.DisplayRole) and (attribute == 'transmission'):
            return f'{sample.transmission[0]:.4f}'
        elif (role == QtCore.Qt.ItemDataRole.EditRole) and (
                attribute in ['positionx', 'positiony', 'thickness', 'distminus', 'transmission']):
            return getattr(sample, attribute)
        elif role == QtCore.Qt.ItemDataRole.DecorationRole:
            return QtGui.QIcon.fromTheme('lock') if sample.isLocked(attribute) else None
        elif (role == QtCore.Qt.ItemDataRole.ToolTipRole) and (attribute == 'title'):
            return sample.description
        elif (role == QtCore.Qt.ItemDataRole.ToolTipRole) and (
                attribute in ['positionx', 'positiony', 'thickness', 'distminus', 'transmission']):
            attr = getattr(sample, attribute)
            return f'{attr[0]:.4f} \xb1 {attr[1]:.4f}'
        elif role == QtCore.Qt.ItemDataRole.UserRole:
            return sample
        else:
            return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        sample = self._samples[index.row()]
        attribute = self._columns[index.column()][0]
        if role == QtCore.Qt.ItemDataRole.EditRole:
            try:
                return self.updateSample(sample.title, attribute, value)
            except Exception:
                return False

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        sample = self._samples[index.row()]
        attr = self._columns[index.column()][0]
        if sample.isLocked(attr):
            return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsDragEnabled | \
                   QtCore.Qt.ItemFlag.ItemIsEnabled  # note that if it is not enabled, we cannot select it!
        else:
            return QtCore.Qt.ItemFlag.ItemNeverHasChildren | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsDragEnabled | \
                   QtCore.Qt.ItemFlag.ItemIsEditable | QtCore.Qt.ItemFlag.ItemIsEnabled

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
        if (orientation == QtCore.Qt.Orientation.Horizontal) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return self._columns[section][1]

    def mimeData(self, indexes: Iterable[QtCore.QModelIndex]) -> QtCore.QMimeData:
        md = QtCore.QMimeData()
        samples = [self._samples[i.row()] for i in indexes]
        md.setData('application/x-cctsamplelist', pickle.dumps(samples))
        return md

    def mimeTypes(self) -> List[str]:
        return ['application/x-cctsamplelist']

    def supportedDragActions(self) -> QtCore.Qt.DropAction:
        return QtCore.Qt.DropAction.CopyAction

    def __contains__(self, item: str) -> bool:
        return item in [s.title for s in self._samples]

    def samples(self):
        yield from self._samples

    def get(self, item: Union[str, int]) -> Sample:
        return copy.deepcopy([s for i, s in enumerate(self._samples) if (s.title == item) or (i == item)][0])

#    def __iter__(self) -> Iterable[Sample]:
#        yield from self._samples
#
#    def __getitem__(self, item: Union[str, int]) -> Sample:
#        return copy.deepcopy([s for i, s in enumerate(self._samples) if (s.title == item) or (i == item)][0])
#
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
            if value in self._samples:
                raise ValueError(
                    f'Cannot rename sample {sample.title} to {value}: another sample with this title already exists.')
        elif attribute == 'maskoverride' and isinstance(value, str) and not value.strip():
            value = None
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
        if prefix not in self._samples:
            return prefix
        i = 0
        while (sn := f'{prefix}_{i}') in self._samples:
            i += 1
        return sn

    def addSample(self, samplename: Optional[str] = None, sample: Optional[Sample] = None) -> str:
        logger.debug('Adding a sample')
        if (samplename is not None) and (samplename in self._samples):
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
        if ('services', 'samplestore', 'list') in self.cfg:
            for sample in self.cfg['services',  'samplestore',  'list']:
                self._samples.append(Sample.fromdict(self.cfg['services',  'samplestore',  'list',  sample]))
        if ('services', 'samplestore', 'active') in self.cfg and (
                self.cfg['services',  'samplestore',  'active'] in self._samples):
            self.setCurrentSample(self.cfg['services',  'samplestore',  'active'])
        else:
            self.setCurrentSample(None)
        self.endResetModel()

    def saveToConfig(self):
        self.cfg.setdefault(('services', 'samplestore', 'list'), {})
        self.cfg.updateAt(('services', 'samplestore', 'list'), {s.title: s.todict() for s in self._samples})
        self.cfg['services', 'samplestore', 'active'] = self._currentsample

    def setCurrentSample(self, title: Optional[str]):
        if title is None:
            self._currentsample = None
            self.currentSampleChanged.emit(None)
            self.saveToConfig()
        elif title in self._samples:
            self._currentsample = title
            self.currentSampleChanged.emit(title)
            self.saveToConfig()
        else:
            raise ValueError(f'Unknown sample "{title}"')

    def currentSample(self) -> Optional[Sample]:
        if self._currentsample is None:
            return None
        return self.get(self._currentsample)

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
        if self._panicking != self.PanicState.NoPanic:
            raise RuntimeError('Cannot move to sample: panicking!')
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

    @Slot(float, float, float)
    def onMotorMoving(self, current: float, start: float, end: float):
        self.movingToSample.emit(self._currentsample, self.sender().name, current, start, end)

    @Slot(float)
    def onMotorStarted(self, start: float):
        pass

    @Slot(bool, float)
    def onMotorStopped(self, success: bool, end: float):
        logger.debug(f'Motor {self.sender().name} stopped. Success: {success}. End: {end:.4f}')
        if not success:
            self._disconnectSampleMotors()
            self.movingFinished.emit(False, self._currentsample)
            if self._panicking == self.PanicState.Panicking:
                super().panichandler()
            return
        if self._panicking == self.PanicState.Panicking:
            super().panichandler()
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

    def panichandler(self):
        self._panicking = self.PanicState.Panicking
        try:
            if not (self.xmotor().isMoving() or self.ymotor().isMoving()):
                super().panichandler()
            else:
                self.stopMotors()
        except KeyError:
            # either motor does not exist
            super().panichandler()

    def sortedSamplesOfCategory(self, category: Sample.Categories) -> QtCore.QSortFilterProxyModel:
        model = QtCore.QSortFilterProxyModel()
        model.setSourceModel(self)
        model.sort(0, QtCore.Qt.SortOrder.AscendingOrder)
        model.setFilterRegularExpression(
            QtCore.QRegularExpression(
                f"^{category.value}$",
                QtCore.QRegularExpression.PatternOption.NoPatternOption))
        model.setFilterKeyColumn([i for i in range(len(self._columns)) if self._columns[i][0] == 'category'][0])
        model.setFilterRole(QtCore.Qt.ItemDataRole.DisplayRole)
        return model
