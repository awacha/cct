import enum
import logging
import pickle
import traceback
from typing import List, Tuple, Any, Optional, Iterable, Union

import numpy as np
from PyQt5 import QtCore, QtGui

from .beamstop import BeamStop
from .component import Component
from .expose import Exposer
from .samples import SampleStore
from ...dataclasses import Sample, Exposure
from ...devices.xraysource.genix.frontend import GeniX, GeniXBackend
from ...algorithms.orderforleastmotormovement import orderForLeastMotorMovement

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class TransmissionData:
    samplename: str
    darkcounts: List[float]
    emptycounts: List[float]
    samplecounts: List[float]

    def __init__(self, samplename: str):
        self.samplename = samplename
        self.darkcounts = []
        self.emptycounts = []
        self.samplecounts = []

    def addDark(self, value: float):
        self.darkcounts.append(value)

    def addEmpty(self, value: float):
        self.emptycounts.append(value)

    def addSample(self, value: float):
        self.samplecounts.append(value)

    def transmission(self, sd_from_error_propagation: bool=True) -> Optional[Tuple[float, float]]:
        if sd_from_error_propagation:
            empty = self.empty()
            dark = self.dark()
            sample = self.sample()
            if (empty is None) or (dark is None) or (sample is None):
                return None
            empty = (empty[0] - dark[0]), (empty[1] ** 2 + dark[1] ** 2) ** 0.5
            sample = (sample[0] - dark[0]), (sample[1] ** 2 + dark[1] ** 2) ** 0.5
            return sample[0] / empty[0], (
                    sample[1] ** 2 / empty[0] ** 2 + empty[1] ** 2 * sample[0] ** 2 / empty[0] ** 4) ** 0.5
        else:
            # calculate the transmission from the standard deviation of several attempts
            if not ((len(self.emptycounts) == len(self.darkcounts)) and (len(self.samplecounts) == len(self.darkcounts))):
                raise ValueError('The number of measurements from dark, empty and sample are not the same!')
            t = [(s-d)/(e-d) for d,e,s in zip(self.darkcounts, self.emptycounts, self.samplecounts)]
            return float(np.nanmean(t)), float(np.nanstd(t))

    def dark(self) -> Optional[Tuple[float, float]]:
        if not self.darkcounts:
            return None
        return float(np.mean(self.darkcounts)), float(np.std(self.darkcounts))

    def empty(self) -> Optional[Tuple[float, float]]:
        if not self.emptycounts:
            return None
        return float(np.mean(self.emptycounts)), float(np.std(self.emptycounts))

    def sample(self) -> Optional[Tuple[float, float]]:
        if not self.samplecounts:
            return None
        return float(np.mean(self.samplecounts)), float(np.std(self.samplecounts))

    def clear(self):
        self.samplecounts = []
        self.darkcounts = []
        self.emptycounts = []


class TransmissionMeasurementStatus(enum.Enum):
    Idle = 'Idle'
    XraysToStandby = 'X-ray generator to standby mode'
    BeamstopOut = 'Moving beam-stop out'
    BeamstopIn = 'Moving beam-stop in'
    OpenShutter = 'Opening shutter'
    CloseShutter = 'Closing shutter'
    ExposingEmpty = 'Exposing empty beam'
    ExposingDark = 'Exposing dark'
    ExposingSample = 'Exposing sample'
    MovingToEmpty = 'Moving to empty beam position'
    MovingToSample = 'Moving to sample position'
    Stopping = 'Stop requested by the user'


class TransmissionMeasurement(QtCore.QAbstractItemModel, Component):
    """Transmission measurement sequence:

    1. Initialization
        1.1. Close beam shutter
        1.2. X-ray source to low-power / standby mode
        1.3. Beamstop out
    2. Exposures
        2.1. Ensure that the beam shutter is closed
        2.2. Expose dark image
        2.3. Move to the empty-beam position
        2.4. Open beam shutter
        2.5. Expose
        2.6. Close beam shutter
        2.7. Move to sample
        2.8. Open beam shutter
        2.9. Expose
        2.10. Close beam shutter
        2.11. Return to 2.1 for the next sample
    3. Finalization
        3.1 Ensure that the beam shutter is closed
        3.2 Move beam-stop in
        3.3. Wait for images to be received

    If an error happens
    """

    lazymode: bool
    _data: List[TransmissionData]
    status: TransmissionMeasurementStatus = TransmissionMeasurementStatus.Idle
    currentlymeasuredsample: Optional[int] = None
    emptysample: str
    countingtime: float
    delaytime: float
    nimages: int
    waitingforimages: Optional[int] = None
    progress = QtCore.pyqtSignal(float, float, float, str)  # minimum, maximum, current, message
    sampleStarted = QtCore.pyqtSignal(str, int, int)  # sample name, index, number of samples
    finished = QtCore.pyqtSignal(bool, str)
    started = QtCore.pyqtSignal()

    def __init__(self, **kwargs):
        self._data = []
        super().__init__(**kwargs)
        if 'transmission' not in self.config:
            self.config['transmission'] = {}
        if 'sd_from_error_propagation' not in self.config['transmission']:
            self.config['transmission']['sd_from_error_propagation'] = True

    def setStatus(self, status: TransmissionMeasurementStatus):
        logger.debug(f'Transmission status: {status}')
        self.status = status

    def startComponent(self):
        self.instrument.samplestore.sampleListChanged.connect(self.onSampleListChanged)

    def onSampleListChanged(self):
        # see if some samples vanished
        vanishedsamples = [data.samplename for data in self._data if data.samplename not in self.instrument.samplestore]
        for sample in vanishedsamples:
            self.removeSample(sample)  # ToDo: what happens if we are currently measuring?
        # update mu and 1/mu if thicknesses changed.
        self.beginResetModel()
        self.endResetModel()

    # QAbstractItemModel reimplemented methods

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return len(self._data)

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 7

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return ['Sample name', 'Dark', 'Empty', 'Sample', 'Transmission', 'Mu (1/cm)', 'Absorption length (cm)'][
                section]

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        data = self._data[index.row()]
        if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
            return data.samplename
        elif (index.column() == 0) and (role == QtCore.Qt.DecorationRole):
            return QtGui.QIcon.fromTheme(
                'media-playback-start') if index.row() == self.currentlymeasuredsample else None
        elif role == QtCore.Qt.BackgroundColorRole:
            return QtGui.QColor(QtCore.Qt.green) if index.row() == self.currentlymeasuredsample else None
        elif (index.column() == 1) and (role == QtCore.Qt.DisplayRole):
            value = data.dark()
            return '--' if value is None else f'{value[0]:.1f} \xb1 {value[1]:.1f}'
        elif (index.column() == 2) and (role == QtCore.Qt.DisplayRole):
            value = data.empty()
            return '--' if value is None else f'{value[0]:.1f} \xb1 {value[1]:.1f}'
        elif (index.column() == 3) and (role == QtCore.Qt.DisplayRole):
            value = data.sample()
            return '--' if value is None else f'{value[0]:.1f} \xb1 {value[1]:.1f}'
        elif (index.column() == 4) and (role == QtCore.Qt.DisplayRole):
            value = data.transmission(self.config['transmission']['sd_from_error_propagation'])
            return '--' if value is None else f'{value[0]:.4f} \xb1 {value[1]:.4f}'
        elif (index.column() == 5) and (role == QtCore.Qt.DisplayRole):
            transm = data.transmission(self.config['transmission']['sd_from_error_propagation'])
            if transm is None:
                return '--'
            mud = -np.log(transm[0]), np.abs(transm[1] / transm[0])
            sample = self.instrument.samplestore[data.samplename]
            assert isinstance(sample, Sample)
            mu = mud[0] / sample.thickness[0], (
                    mud[1] ** 2 / sample.thickness[0] ** 2 + mud[0] ** 2 * sample.thickness[1] ** 2 /
                    sample.thickness[0] ** 4) ** 0.5
            return f'{mu[0]:.4f} \xb1 {mu[1]:.4f}'
        elif (index.column() == 6) and (role == QtCore.Qt.DisplayRole):
            transm = data.transmission(self.config['transmission']['sd_from_error_propagation'])
            if transm is None:
                return '--'
            mud = -np.log(transm[0]), np.abs(transm[1] / transm[0])
            sample = self.instrument.samplestore[data.samplename]
            assert isinstance(sample, Sample)
            invmu = sample.thickness[0] / mud[0], (
                    sample.thickness[1] ** 2 / mud[0] ** 2 + sample.thickness[0] ** 2 * mud[1] ** 2 / mud[
                0] ** 4) ** 0.5
            return f'{invmu[0]:.4f} \xb1 {invmu[1]:.4f}'
        elif (index.column() == 1) and (role == QtCore.Qt.ToolTipRole):
            if not data.darkcounts:
                return 'No measurements yet'
            else:
                return ', '.join([str(x) for x in data.darkcounts]) + f'({len(data.darkcounts)} measurements)'
        elif (index.column() == 2) and (role == QtCore.Qt.ToolTipRole):
            if not data.emptycounts:
                return 'No measurements yet'
            else:
                return ', '.join([str(x) for x in data.empty()]) + f'({len(data.emptycounts)} measurements)'
        elif (index.column() == 3) and (role == QtCore.Qt.ToolTipRole):
            if not data.samplecounts:
                return 'No measurements yet'
            else:
                return ', '.join([str(x) for x in data.samplecounts]) + f'({len(data.samplecounts)} measurements)'

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if self.status == TransmissionMeasurementStatus.Idle:
            if index.isValid():
                return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
            else:
                return QtCore.Qt.ItemIsDropEnabled | QtCore.Qt.ItemIsEnabled
        else:
            return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        self.beginRemoveRows(parent, row, row+count)
        self._data = self._data[:row] + self._data[row+count:]
        self.endRemoveRows()
        return True

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.removeRows(row, 1, parent)

    def supportedDropActions(self) -> QtCore.Qt.DropAction:
        return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction

    def supportedDragActions(self) -> QtCore.Qt.DropAction:
        return QtCore.Qt.MoveAction

    def mimeTypes(self) -> List[str]:
        return ['application/x-cctsamplelist', 'application/x-ccttransmissiondata']

    def mimeData(self, indexes: Iterable[QtCore.QModelIndex]) -> QtCore.QMimeData:
        md = QtCore.QMimeData()
        samplenames = [self._data[index.row()].samplename for index in indexes]
        samples = [s for s in self.instrument.samplestore if s.title in samplenames]
        md.setData('application/x-cctsamplelist', pickle.dumps(samples))
        td = [self._data[index.row()] for index in indexes]
        md.setData('application/x-ccttransmissiondata', pickle.dumps(td))
        return md

    def dropMimeData(self, data: QtCore.QMimeData, action: QtCore.Qt.DropAction, row: int, column: int,
                     parent: QtCore.QModelIndex) -> bool:
        if action != QtCore.Qt.CopyAction:
            pass
        if parent.isValid():
            row = parent.row()
        logger.debug(f'dropping MIME data to {row=}, {column=}, {parent=}, {action=}')
        if row < 0:
            row = self.rowCount(QtCore.QModelIndex())
        if data.hasFormat('application/x-ccttransmissiondata'):
            tdata: List[TransmissionData] = pickle.load(data.data('application/x-ccttransmissiondata'))
            if not tdata:
                return False
            self.beginInsertRows(QtCore.QModelIndex(), row, row+len(tdata)-1)
            self._data = self._data[:row] + tdata + self._data[row:]
            self.endInsertRows()
        elif data.hasFormat('application/x-cctsamplelist'):
            samples: List[Sample] = pickle.loads(data.data('application/x-cctsamplelist'))
            samples = [s for s in samples if s.title not in [d.samplename for d in self._data]]
            if not samples:
                return False
            self.beginInsertRows(QtCore.QModelIndex(), row, row + len(samples) - 1)
            self._data = self._data[:row] + [TransmissionData(s.title) for s in samples] + self._data[row:]
            self.endInsertRows()
        return True

    # Add, remove, clear transmission tasks...

    def addSample(self, samplename: str):
        if self.status != TransmissionMeasurementStatus.Idle:
            raise RuntimeError('Cannot add sample: currently measuring transmission')
        if samplename in [data.samplename for data in self._data]:
            raise RuntimeError(f'Cannot add duplicate sample "{samplename}"')
        self.beginInsertRows(QtCore.QModelIndex(), len(self._data), len(self._data))
        self._data.append(TransmissionData(samplename))
        self.endInsertRows()

    def removeSample(self, samplename: str):
        if self.status != TransmissionMeasurementStatus.Idle:
            raise RuntimeError('Cannot remove sample: currently measuring transmission')
        row = [i for i, data in enumerate(self._data) if data.samplename == samplename][0]
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._data[row]
        self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    # convenience properties to access X-ray source, beamstop, exposer, sample store

    @property
    def source(self) -> GeniX:
        source = self.instrument.devicemanager.source()
        assert isinstance(source, GeniX)
        return source

    @property
    def beamstop(self) -> BeamStop:
        return self.instrument.beamstop

    @property
    def exposer(self) -> Exposer:
        return self.instrument.exposer

    @property
    def samplestore(self) -> SampleStore:
        return self.instrument.samplestore

    # connect/disconnect signal handlers to/from X-ray source, beamstop, exposer, sample store

    def _connectSource(self):
        self.source.shutter.connect(self.onShutter)
        self.source.powerStateChanged.connect(self.onXraySourcePowerStateChanged)

    def _disconnectSource(self):
        try:
            self.source.shutter.disconnect(self.onShutter)
        except TypeError:
            pass
        try:
            self.source.powerStateChanged.disconnect(self.onXraySourcePowerStateChanged)
        except TypeError:
            pass

    def _connectBeamStop(self):
        self.beamstop.stateChanged.connect(self.onBeamStopStateChanged)

    def _disconnectBeamStop(self):
        try:
            self.beamstop.stateChanged.disconnect(self.onBeamStopStateChanged)
        except TypeError:
            pass

    def _connectSampleStore(self):
        self.samplestore.movingFinished.connect(self.onMovingToSampleFinished)
        self.samplestore.movingToSample.connect(self.onMovingToSampleProgress)

    def _disconnectSampleStore(self):
        try:
            self.samplestore.movingFinished.disconnect(self.onMovingToSampleFinished)
        except TypeError:
            pass
        try:
            self.samplestore.movingToSample.disconnect(self.onMovingToSampleProgress)
        except TypeError:
            pass

    def _connectExposer(self):
        self.exposer.exposureFinished.connect(self.onExposureFinished)
        self.exposer.exposureProgress.connect(self.onExposureProgress)
        self.exposer.imageReceived.connect(self.onImageReceived)

    def _disconnectExposer(self):
        try:
            self.exposer.exposureFinished.disconnect(self.onExposureFinished)
        except TypeError:
            pass
        try:
            self.exposer.exposureProgress.disconnect(self.onExposureProgress)
        except TypeError:
            pass
        try:
            self.exposer.imageReceived.disconnect(self.onImageReceived)
        except TypeError:
            pass

    # start the measurement

    def startMeasurement(self, emptysample: str, countingtime: float, nimages: int, delaytime: float,
                         lazymode: bool = False):
        if self._panicking != self.PanicState.NoPanic:
            raise RuntimeError('Cannot start transmission measurement: in panic state!')
        if self.status != TransmissionMeasurementStatus.Idle:
            raise RuntimeError('Cannot start transmission measurement: already running')
        self.emptysample = emptysample
        self.countingtime = countingtime
        self.nimages = nimages
        self.delaytime = delaytime
        self.lazymode = lazymode
        self.currentlymeasuredsample = None
        self.beginResetModel()
        for data in self._data:
            data.clear()
        if self.lazymode:
            self.orderSamplesForLeastMovement()
        self.endResetModel()
        self.started.emit()
        self.closeShutter()

    def stopMeasurement(self):
        if self.status == TransmissionMeasurementStatus.ExposingDark:
            self.exposer.stopExposure()
        elif self.status == TransmissionMeasurementStatus.ExposingEmpty:
            self.exposer.stopExposure()
        elif self.status == TransmissionMeasurementStatus.ExposingSample:
            self.exposer.stopExposure()
        elif self.status == TransmissionMeasurementStatus.MovingToSample:
            self.samplestore.stopMotors()
        elif self.status == TransmissionMeasurementStatus.Idle:
            return
        elif self.status == TransmissionMeasurementStatus.MovingToEmpty:
            self.samplestore.stopMotors()
        elif self.status == TransmissionMeasurementStatus.BeamstopOut:
            self.beamstop.stopMoving()
        elif self.status == TransmissionMeasurementStatus.BeamstopIn:
            self.beamstop.stopMoving()
        elif self.status == TransmissionMeasurementStatus.CloseShutter:
            pass
        elif self.status == TransmissionMeasurementStatus.OpenShutter:
            pass
        elif self.status == TransmissionMeasurementStatus.XraysToStandby:
            pass
        else:
            pass
        self.setStatus(TransmissionMeasurementStatus.Stopping)

    # various tasks: opening/closing shutter, X-ray source to standby mode, beamstop out/in, exposing etc.

    def finishIfUserStop(self) -> bool:
        if self.status == TransmissionMeasurementStatus.Stopping:
            try:
                self._disconnectSource()
            except TypeError:
                pass
            try:
                self._disconnectSampleStore()
            except TypeError:
                pass
            try:
                self._disconnectBeamStop()
            except TypeError:
                pass
            try:
                self._disconnectExposer()
            except TypeError:
                pass
            logger.error('Transmission measurement stopped on user request')
            self.finish(False, 'Transmission measurement stopped on user request')
            return True
        else:
            return False

    def closeShutter(self):
        if self.finishIfUserStop():
            return
        self.setStatus(TransmissionMeasurementStatus.CloseShutter)
        if not self.source['shutter']:
            self.onShutter(False)
        else:
            self._connectSource()
            try:
                self.source.moveShutter(False)
                self.progress.emit(0, 0, 0, 'Closing beam shutter')
            except Exception as exc:
                self._disconnectSource()
                self.finish(False, str(exc))

    def openShutter(self):
        if self.finishIfUserStop():
            return
        self.setStatus(TransmissionMeasurementStatus.OpenShutter)
        if self.source['shutter']:
            self.onShutter(True)
        else:
            self._connectSource()
            try:
                self.source.moveShutter(True)
                self.progress.emit(0, 0, 0, 'Opening beam shutter')
            except Exception as exc:
                self._disconnectSource()
                self.finish(False, str(exc))

    def xraysToStandby(self):
        if self.finishIfUserStop():
            return
        self.setStatus(TransmissionMeasurementStatus.XraysToStandby)
        if self.source['__status__'] == GeniXBackend.Status.standby:
            self.onXraySourcePowerStateChanged(GeniXBackend.Status.standby)
        else:
            self._connectSource()
            try:
                self.source.standby()
                self.progress.emit(0, 0, 0, 'Putting X-ray source to standby mode')
            except Exception as exc:
                self._disconnectSource()
                self.finish(False, str(exc))

    def beamstopOut(self):
        if self.finishIfUserStop():
            return
        self.setStatus(TransmissionMeasurementStatus.BeamstopOut)
        if self.beamstop.checkState() == self.beamstop.States.Out:
            self.onBeamStopStateChanged(self.beamstop.States.Out.value)
        else:
            self._connectBeamStop()
            try:
                self.beamstop.moveOut()
                self.progress.emit(0, 0, 0, 'Moving beamstop out')
            except Exception as exc:
                self._disconnectSource()
                self.finish(False, str(exc))

    def beamstopIn(self):
        if self.finishIfUserStop():
            return
        self.setStatus(TransmissionMeasurementStatus.BeamstopIn)
        if self.beamstop.checkState() == self.beamstop.States.In:
            self.onBeamStopStateChanged(self.beamstop.States.In.value)
        else:
            self._connectBeamStop()
            try:
                self.beamstop.moveIn()
                self.progress.emit(0, 0, 0, 'Moving beamstop in')
            except Exception as exc:
                self._disconnectSource()
                self.finish(False, str(exc))

    def moveSample(self):
        if self.finishIfUserStop():
            return
        samplename = self._data[self.currentlymeasuredsample].samplename
        self._connectSampleStore()
        try:
            self.samplestore.moveToSample(samplename)
            self.samplestore.setCurrentSample(samplename)
            self.setStatus(TransmissionMeasurementStatus.MovingToSample)
        except Exception as exc:
            self._disconnectSampleStore()
            self.finish(False, str(exc))

    def moveEmpty(self):
        if self.finishIfUserStop():
            return
        self._connectSampleStore()
        try:
            self.samplestore.moveToSample(self.emptysample)
            self.setStatus(TransmissionMeasurementStatus.MovingToEmpty)
        except Exception as exc:
            self._disconnectSampleStore()
            self.finish(False, str(exc))

    def expose(self):
        if self.finishIfUserStop():
            return
        self._connectExposer()
        try:
            if self._data[self.currentlymeasuredsample].dark() is None:
                # expose dark
                logger.debug('Exposing dark')
                self.setStatus(TransmissionMeasurementStatus.ExposingDark)
            elif self._data[self.currentlymeasuredsample].empty() is None:
                # expose empty
                logger.debug('Exposing empty')
                self.setStatus(TransmissionMeasurementStatus.ExposingEmpty)
            else:
                assert self._data[self.currentlymeasuredsample].sample() is None
                # expose sample
                logger.debug('Exposing sample')
                self.setStatus(TransmissionMeasurementStatus.ExposingSample)
            self.waitingforimages = self.nimages
            self.instrument.exposer.startExposure(self.config['path']['prefixes']['tra'],
                                                  exposuretime=self.countingtime,
                                                  delay=self.delaytime, imagecount=self.nimages)
        except Exception as exc:
            self._disconnectExposer()
            self.finish(False, str(exc))

    def finish(self, success: bool, message: str):
        self.setStatus(TransmissionMeasurementStatus.Idle)
        self.currentlymeasuredsample = None
        self.dataChanged.emit(
            self.index(0, 0, QtCore.QModelIndex()),
            self.index(self.rowCount(QtCore.QModelIndex()),
                       self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))
        self._disconnectExposer()
        self._disconnectSource()
        self._disconnectBeamStop()
        self._disconnectSampleStore()
        try:
            self.finished.emit(success, message)
        except Exception as exc:
            logger.error(f'Exception in transmission.finished() callback: {traceback.format_exc()}')
        if self._panicking == self.PanicState.Panicking:
            logger.error('Transmission measurement stopped on panic!')
            super().panichandler()

    # slots for checking the outcome of the above commands

    def onShutter(self, shutterstate: bool):
        if self.finishIfUserStop():
            return
        if (self.status == TransmissionMeasurementStatus.CloseShutter) and (not shutterstate):
            # shutter closed successfully
            self._disconnectSource()
            if self.currentlymeasuredsample is None:
                # we are in the initialization phase, X-ray source must be turned to standby mode
                self.xraysToStandby()
            else:
                # we are in the sample measuring phase. We need to move the sample stage or go to the next sample
                currenttask = self._data[self.currentlymeasuredsample]
                if currenttask.dark() is None:
                    # should not happen, see below.
                    assert False
                elif currenttask.empty() is None:
                    # we are just ready with the dark measurement, move to the empty beam position
                    self.moveEmpty()
                elif currenttask.sample() is None:
                    # we are just ready with the empty measurement, move to the sample position
                    self.moveSample()
                else:
                    # we are just ready with exposing the sample. Save the transmission if possible.
                    self.saveTransmissionResult(self.currentlymeasuredsample)
                    # go to the next sample
                    if self.currentlymeasuredsample >= (len(self._data) - 1):
                        # no more samples to measure
                        self.currentlymeasuredsample = None
                        self.dataChanged.emit(self.index(self.rowCount(QtCore.QModelIndex()), 0, QtCore.QModelIndex()),
                                              self.index(self.rowCount(QtCore.QModelIndex()),
                                                         self.columnCount(QtCore.QModelIndex()),
                                                         QtCore.QModelIndex()))
                        self.beamstopIn()
                    else:
                        # advance to the next sample
                        self.currentlymeasuredsample += 1
                        self.dataChanged.emit(self.index(self.currentlymeasuredsample - 1, 0, QtCore.QModelIndex()),
                                              self.index(self.currentlymeasuredsample,
                                                         self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex()))
                        self.sampleStarted.emit(self._data[self.currentlymeasuredsample].samplename,
                                                self.currentlymeasuredsample, len(self._data))
                        # expose dark
                        if self._data[self.currentlymeasuredsample].dark() is None:
                            self.expose()
                        elif self._data[self.currentlymeasuredsample].empty() is None:
                            # this can happen in lazy mode: the first dark measurement is used for all samples.
                            self.moveEmpty()
                        else:
                            # this can happen in lazy mode: the first empty measurement is used for all samples.
                            assert self._data[self.currentlymeasuredsample].sample() is None
                            # the sample must not have been measured yet!
                            self.moveSample()
        elif (self.status == TransmissionMeasurementStatus.OpenShutter) and shutterstate:
            # shutter opened successfully, start the exposure
            self._disconnectSource()
            self.expose()
        elif self.status not in [TransmissionMeasurementStatus.OpenShutter, TransmissionMeasurementStatus.CloseShutter]:
            # shutter opened or closed for a different reason, disregard this
            logger.warning(f'Shutter unexpectedly {"opened" if shutterstate else "closed"} during transmission '
                           f'measurement.')
        else:
            # shutter remained open when requested to be closed or could not open: this is an error
            self._disconnectSource()
            self.finish(False, "Shutter error")

    def saveTransmissionResult(self, samplename: Union[str, int]):
        if isinstance(samplename, str):
            sampleindex = [i for i in range(len(self._data)) if self._data[i].samplename == samplename][0]
        elif isinstance(samplename, int):
            sampleindex = samplename
            samplename = self._data[sampleindex].samplename
        currenttask = self._data[sampleindex]
        transm = currenttask.transmission(self.config['transmission']['sd_from_error_propagation'])
        logger.info(f'Transmission for sample {samplename} is: '
                    f'{transm[0]:.4f} \xb1 {transm[1]:.4f}')
        try:
            self.samplestore.updateSample(samplename, 'transmission', transm)
        except ValueError as ve:
            logger.error(f'Cannot set transmission of sample {samplename}: {str(ve)}')

    def onImageReceived(self, exposure: Exposure):
        if self.finishIfUserStop():
            return
        assert self.status in [TransmissionMeasurementStatus.ExposingDark, TransmissionMeasurementStatus.ExposingSample,
                               TransmissionMeasurementStatus.ExposingEmpty]
        self.waitingforimages -= 1
        counts = exposure.intensity[exposure.intensity > 0].sum()
        logger.debug(
            f'Exposure image {exposure.header.fsn=} received. Counts: {counts}. Sample: {self.currentlymeasuredsample}. Status: {self.status}. Waiting for {self.waitingforimages} more images.')
        data = self._data[self.currentlymeasuredsample]
        if self.status == TransmissionMeasurementStatus.ExposingDark:
            data.darkcounts.append(counts)
        elif self.status == TransmissionMeasurementStatus.ExposingEmpty:
            data.emptycounts.append(counts)
        elif self.status == TransmissionMeasurementStatus.ExposingSample:
            data.samplecounts.append(counts)
        else:
            assert False
        if self.waitingforimages <= 0:
            # all images are received.
            logger.debug(f'All images received for sample {self.currentlymeasuredsample}, {self.status}')
            self._disconnectExposer()
            if (self.lazymode and
                    (self.status in [TransmissionMeasurementStatus.ExposingDark,
                                     TransmissionMeasurementStatus.ExposingEmpty]) and (
                            self.currentlymeasuredsample == 0)):
                for i in range(1, len(self._data)):
                    if self.status == TransmissionMeasurementStatus.ExposingDark:
                        self._data[i].darkcounts = list(self._data[0].darkcounts)
                    elif self.status == TransmissionMeasurementStatus.ExposingEmpty:
                        self._data[i].emptycounts = list(self._data[0].emptycounts)
                    else:
                        pass
            self.dataChanged.emit(self.index(0, 1, QtCore.QModelIndex()),
                                  self.index(self.rowCount(), self.columnCount(), QtCore.QModelIndex()))
            if self.status == TransmissionMeasurementStatus.ExposingDark:
                self.moveEmpty()
            elif self.status == TransmissionMeasurementStatus.ExposingEmpty:
                self.closeShutter()
            elif self.status == TransmissionMeasurementStatus.ExposingSample:
                self.closeShutter()
            else:
                assert False
        else:
            pass

    def onExposureFinished(self, success: bool):
        if self.finishIfUserStop():
            return
        if not success:
            self._disconnectExposer()
            self.finish(False, f'Error in exposure')
        else:
            # pass, finish this step when all images are received.
            pass

    def onExposureProgress(self, prefix: str, fsn: int, currenttime: float, starttime: float, endtime: float):
        if self.finishIfUserStop():
            return
        self.progress.emit(starttime, endtime, currenttime, 'Exposing...')

    def onBeamStopStateChanged(self, state: str):
        if self.finishIfUserStop():
            return
        if (state == BeamStop.States.Out.value) and (self.status == TransmissionMeasurementStatus.BeamstopOut):
            self._disconnectBeamStop()
            self.currentlymeasuredsample = 0
            self.dataChanged.emit(self.index(self.currentlymeasuredsample, 0, QtCore.QModelIndex()),
                                  self.index(self.currentlymeasuredsample, self.columnCount(QtCore.QModelIndex()),
                                             QtCore.QModelIndex()))
            self.sampleStarted.emit(self._data[self.currentlymeasuredsample].samplename, 0, len(self._data))
            self.expose()  # start exposing the sample
        elif (state == BeamStop.States.In.value) and (self.status == TransmissionMeasurementStatus.BeamstopIn):
            # transmission measurement finished.
            self._disconnectBeamStop()
            self.finish(True, 'Successfully finished transmission measurement sequence')
        elif (self.status in [TransmissionMeasurementStatus.BeamstopIn,
                              TransmissionMeasurementStatus.BeamstopOut]) and (
                state in [BeamStop.States.Moving, BeamStop.States.Undefined]):
            # moving beamstop
            pass
        else:
            pass

    #            logger.warning(f'Unexpected Beamstop motion during transmission measurement: {self.status=}, {state=}.')

    def onXraySourcePowerStateChanged(self, value: str):
        if self.finishIfUserStop():
            return
        if (self.status == TransmissionMeasurementStatus.XraysToStandby) and (value == GeniXBackend.Status.standby):
            # successful, move out beamstop
            self._disconnectSource()
            self.beamstopOut()
        else:
            pass

    def onMovingToSampleFinished(self, success: bool, samplename: str):
        if self.finishIfUserStop():
            return
        if success and (self.status in [TransmissionMeasurementStatus.MovingToEmpty,
                                        TransmissionMeasurementStatus.MovingToSample]):
            self._disconnectSampleStore()
            self.openShutter()
        elif not success:
            self._disconnectSampleStore()
            self.finish(False, f'Cannot move to sample {samplename}.')

    def onMovingToSampleProgress(self, samplename: str, motorname: str, current: float, start: float, end: float):
        self.progress.emit(start, end, current, f'Moving to sample {samplename}: motor {motorname} is at {current:.2f}')

    def orderSamplesByName(self):
        self.beginResetModel()
        self._data = sorted(self._data, key=lambda x: x.samplename)
        self.endResetModel()

    def orderSamplesForLeastMovement(self):
        samples = [self.samplestore[d.samplename] for d in self._data]
        empty = self.samplestore[self.emptysample]
        samples_ordered = orderForLeastMotorMovement([(s, (s.positionx[0], s.positiony[0])) for s in samples], (empty.positionx[0], empty.positiony[0]))
        self.beginResetModel()
        sorteddata = [[d for d in self._data if d.samplename == s.title][0] for s in samples_ordered]
        self._data = sorteddata
        self.endResetModel()

    def panichandler(self):
        self._panicking = self.PanicState.Panicking
        if self.status == TransmissionMeasurementStatus.Idle:
            super().panichandler()
        else:
            self.stopMeasurement()

    def saveAllResults(self):
        for i in range(len(self._data)):
            try:
                self.saveTransmissionResult(i)
            except Exception as exc:
                logger.error(f'Cannot save trnasmission of sample {self._data[i].samplename}: {exc}')

    def setErrorPropagationMode(self, sd_from_error_propagation: bool):
        logger.debug(f'setErrorPropagationMode({sd_from_error_propagation})')
        self.config['transmission']['sd_from_error_propagation'] = sd_from_error_propagation

    def onConfigChanged(self, path, value):
        logger.debug(f'onConfigChanged({path}, {value})')
        if path == ('transmission', 'sd_from_error_propagation'):
            logger.debug('Emitting data changed signal.')
            self.dataChanged.emit(self.index(0, 0, QtCore.QModelIndex()),
                                  self.index(self.rowCount(QtCore.QModelIndex()),
                                             self.columnCount(QtCore.QModelIndex())))
