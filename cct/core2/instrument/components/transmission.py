import enum
import logging
from typing import List, Tuple, Any, Optional

import numpy as np
from PyQt5 import QtCore

from .beamstop import BeamStop
from .component import Component
from .expose import Exposer
from .samples import SampleStore
from ...dataclasses import Sample, Exposure
from ...devices.xraysource.genix.frontend import GeniX, GeniXBackend

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

    def transmission(self) -> Optional[Tuple[float, float]]:
        empty = self.empty()
        dark = self.dark()
        sample = self.sample()
        if (empty is None) or (dark is None) or (sample is None):
            return None
        empty = (empty[0] - dark[0]), (empty[1] ** 2 + dark[1] ** 2) ** 0.5
        sample = (sample[0] - dark[0]), (sample[1] ** 2 + dark[1] ** 2) ** 0.5
        return sample[0] / empty[0], (
                    sample[1] ** 2 / dark[0] ** 2 + dark[1] ** 2 * sample[0] ** 2 / dark[0] ** 4) ** 0.5

    def dark(self) -> Optional[Tuple[float, float]]:
        if not self.darkcounts:
            return None
        return np.mean(self.darkcounts), np.std(self.darkcounts)

    def empty(self) -> Optional[Tuple[float, float]]:
        if not self.emptycounts:
            return None
        return np.mean(self.emptycounts), np.std(self.emptycounts)

    def sample(self) -> Optional[Tuple[float, float]]:
        if not self.samplecounts:
            return None
        return np.mean(self.samplecounts), np.std(self.samplecounts)

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
    progress = QtCore.pyqtSignal(float, float, float, str)
    finished = QtCore.pyqtSignal(bool, str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._data = []

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
        elif (index.column() == 1) and (role == QtCore.Qt.DisplayRole):
            value = data.dark()
            return '--' if value is None else f'{value[0]} \xb1 {value[1]}'
        elif (index.column() == 2) and (role == QtCore.Qt.DisplayRole):
            value = data.empty()
            return '--' if value is None else f'{value[0]} \xb1 {value[1]}'
        elif (index.column() == 3) and (role == QtCore.Qt.DisplayRole):
            value = data.sample()
            return '--' if value is None else f'{value[0]} \xb1 {value[1]}'
        elif (index.column() == 4) and (role == QtCore.Qt.DisplayRole):
            value = data.transmission()
            return '--' if value is None else f'{value[0]:.4f} \xb1 {value[1]:.4f}'
        elif (index.column() == 5) and (role == QtCore.Qt.DisplayRole):
            transm = data.transmission()
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
            transm = data.transmission()
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
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    # Add, remove, clear transmission tasks...

    def addSample(self, samplename: str):
        if self.status != TransmissionMeasurementStatus.Idle:
            raise RuntimeError('Cannot add sample: currently measuring transmission')
        if samplename in [data.samplename for data in self._data]:
            raise RuntimeError(f'Cannot add duplicate sample "{samplename}"')
        row = max([i for i, data in enumerate(self._data) if data.samplename < samplename], -1)
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self._data.insert(row, TransmissionData(samplename))
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
        self.closeShutter()

    # various tasks: opening/closing shutter, X-ray source to standby mode, beamstop out/in, exposing etc.

    def closeShutter(self):
        self.status = TransmissionMeasurementStatus.CloseShutter
        if not self.source['shutter']:
            self.onShutter(False)
        else:
            self._connectSource()
            try:
                self.source.moveShutter(False)
                self.progress.emit(0, 0, 0, 'Closing beam shutter')
            except Exception as exc:
                self._disconnectSource()
                self.finished.emit(False, str(exc))

    def openShutter(self):
        self.status = TransmissionMeasurementStatus.OpenShutter
        if self.source['shutter']:
            self.onShutter(True)
        else:
            self._connectSource()
            try:
                self.source.moveShutter(True)
                self.progress.emit(0, 0, 0, 'Opening beam shutter')
            except Exception as exc:
                self._disconnectSource()
                self.finished.emit(False, str(exc))

    def xraysToStandby(self):
        self.status = TransmissionMeasurementStatus.XraysToStandby
        if self.source['__status__'] == GeniXBackend.Status.standby:
            self.onXraySourcePowerStateChanged(GeniXBackend.Status.standby)
        else:
            self._connectSource()
            try:
                self.source.standby()
                self.progress.emit(0, 0, 0, 'Setting X-ray source to standby mode')
            except Exception as exc:
                self._disconnectSource()
                self.finished.emit(False, str(exc))

    def beamstopOut(self):
        self.status = TransmissionMeasurementStatus.BeamstopOut
        if self.beamstop.checkState() == self.beamstop.States.Out:
            self.onBeamStopStateChanged(self.beamstop.States.Out.value)
        else:
            self._connectBeamStop()
            try:
                self.beamstop.moveOut()
                self.progress.emit(0, 0, 0, 'Moving beamstop out')
            except Exception as exc:
                self._disconnectSource()
                self.finished.emit(False, str(exc))

    def beamstopIn(self):
        self.status = TransmissionMeasurementStatus.BeamstopIn
        if self.beamstop.checkState() == self.beamstop.States.In:
            self.onBeamStopStateChanged(self.beamstop.States.In.value)
        else:
            self._connectBeamStop()
            try:
                self.beamstop.moveIn()
                self.progress.emit(0, 0, 0, 'Moving beamstop in')
            except Exception as exc:
                self._disconnectSource()
                self.finished.emit(False, str(exc))

    def moveSample(self):
        samplename = self._data[self.currentlymeasuredsample].samplename
        self._connectSampleStore()
        try:
            self.samplestore.moveToSample(samplename)
            self.status = TransmissionMeasurementStatus.MovingToSample
        except Exception as exc:
            self._disconnectSampleStore()
            self.finished.emit(False, str(exc))

    def moveEmpty(self):
        self._connectSampleStore()
        try:
            self.samplestore.moveToSample(self.emptysample)
            self.status = TransmissionMeasurementStatus.MovingToEmpty
        except Exception as exc:
            self._disconnectSampleStore()
            self.finished.emit(False, str(exc))

    def expose(self):
        self._connectExposer()
        try:
            if self._data[self.currentlymeasuredsample].dark() is None:
                # expose dark
                self.status = TransmissionMeasurementStatus.ExposingDark
            elif self._data[self.currentlymeasuredsample].empty() is None:
                # expose empty
                self.status = TransmissionMeasurementStatus.ExposingEmpty
            else:
                assert self._data[self.currentlymeasuredsample].sample() is None
                # expose sample
                self.status = TransmissionMeasurementStatus.ExposingSample
            self.waitingforimages = self.nimages
            self.instrument.exposer.startExposure(self.config['path']['prefixes']['tra'],
                                                  exposuretime=self.countingtime,
                                                  delay=self.delaytime, imagecount=self.nimages)
        except Exception as exc:
            self._disconnectExposer()
            self.finished.emit(False, str(exc))

    # slots for checking the outcome of the above commands

    def onShutter(self, shutterstate: bool):
        if (self.status == TransmissionMeasurementStatus.CloseShutter) and (not shutterstate):
            # shutter closed successfully
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
                    sample = self.samplestore[currenttask.samplename]
                    transm = currenttask.transmission()
                    logger.info(f'Transmission for sample {sample.title} measured: '
                                f'{transm[0]:.4f} \xb1 {transm[1]:.4f}')
                    try:
                        sample.transmission = transm
                    except ValueError as ve:
                        logger.error(f'Cannot set transmission of sample {sample.title}: {str(ve)}')
                    self.samplestore.updateSample(sample.title, sample)
                    # go to the next sample
                    if self.currentlymeasuredsample >= len(self._data):
                        # no more samples to measure
                        self.beamstopIn()
                    else:
                        # advance to the next sample
                        self.currentlymeasuredsample += 1
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
            self.expose()
        elif self.status not in [TransmissionMeasurementStatus.OpenShutter, TransmissionMeasurementStatus.CloseShutter]:
            # shutter opened or closed for a different reason, disregard this
            logger.warning(f'Shutter unexpectedly {"opened" if shutterstate else "closed"} during transmission '
                           f'measurement.')
        else:
            # shutter remained open when requested to be closed or could not open: this is an error
            self.finished.emit(False, "Shutter error")

    def onImageReceived(self, exposure: Exposure):
        assert self.status in [TransmissionMeasurementStatus.ExposingDark, TransmissionMeasurementStatus.ExposingSample,
                               TransmissionMeasurementStatus.ExposingEmpty]
        self.waitingforimages -= 1
        counts = exposure.intensity[exposure.intensity > 0].sum()
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
            self._disconnectExposer()
            if self.lazymode and (self.status == TransmissionMeasurementStatus.ExposingDark) and (
                    self.currentlymeasuredsample == 0):
                for i in range(1, len(self._data)):
                    if self.status == TransmissionMeasurementStatus.ExposingDark:
                        self._data[i].darkcounts = list(self._data[0].darkcounts)
                    elif self.status == TransmissionMeasurementStatus.ExposingEmpty:
                        self._data[i].emptycounts = list(self._data[0].darkcounts)
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

    def onExposureFinished(self, success: bool, message: str):
        if not success:
            self._disconnectExposer()
            self.finished.emit(False, f'Error in exposure: {message}')
        else:
            # pass, finish this step when all images are received.
            pass

    def onExposureProgress(self, prefix: str, fsn: int, currenttime: float, starttime: float, endtime: float):
        pass

    def onBeamStopStateChanged(self, state: str):
        if (state == BeamStop.States.Out) and (self.status == TransmissionMeasurementStatus.BeamstopOut):
            self._disconnectBeamStop()
            self.currentlymeasuredsample = 0
            self.expose()  # start exposing the sample
        elif (state == BeamStop.States.In) and (self.status == TransmissionMeasurementStatus.BeamstopIn):
            # transmission measurement finished.
            self._disconnectBeamStop()
            self.finished.emit(True, 'Successfully finished transmission measurement sequence')
        elif (self.status in [TransmissionMeasurementStatus.BeamstopIn,
                              TransmissionMeasurementStatus.BeamstopOut]) and (
                state in [BeamStop.States.Moving, BeamStop.States.Undefined]):
            # moving beamstop
            pass
        else:
            logger.warning('Unexpected Beamstop motion during transmission measurement.')

    def onXraySourcePowerStateChanged(self, value: str):
        self.instrument.devicemanager.source().powerStateChanged.disconnect(self.onXraySourcePowerStateChanged)
        if (self.status == TransmissionMeasurementStatus.XraysToStandby) and (value == GeniXBackend.Status.standby):
            # successful, move out beamstop
            self.beamstopOut()
        else:
            pass

    def onMovingToSampleFinished(self, success: bool, samplename: str):
        if success and (self.status in [TransmissionMeasurementStatus.MovingToEmpty,
                                        TransmissionMeasurementStatus.MovingToSample]):
            self._disconnectSampleStore()
            self.openShutter()
        elif not success:
            self._disconnectSampleStore()
            self.finished.emit(False, f'Cannot move to sample {samplename}.')

    def onMovingToSampleProgress(self, samplename: str, motorname: str, current: float, start: float, end: float):
        pass

    def orderSamplesForLeastMovement(self):
        samples = [self.samplestore[d.samplename] for d in self._data]
        empty = self.samplestore[self.emptysample]
        samples_ordered = []
        positions = {s.title: (s.positionx[0], s.positiony[0]) for s in samples}
        ebpos = (empty.positionx[0], empty.positiony[0])

        if len(set([p[0] for p in positions.values()] + [ebpos[0]])) < \
                len(set([p[1] for p in positions.values()] + [ebpos[1]])):
            # there are more unique Y coordinates than X coordinates: go by X coordinates first
            slowestmoving = 0
            fastestmoving = 1
        else:
            slowestmoving = 1
            fastestmoving = 0
        # put the slowest moving sample (not empty!) coordinates first in increasing order
        slow_ordered = sorted(set([p[slowestmoving] for p in positions.values()]))
        # see which end we must start. Start from that end which is nearest to the empty beam measurement
        if abs(slow_ordered[-1] - ebpos[slowestmoving]) < abs(slow_ordered[0] - ebpos[slowestmoving]):
            slow_ordered = reversed(slow_ordered)
        lastfastcoord = ebpos[fastestmoving]
        samplenames_ordered = []
        for slowpos in [ebpos[slowestmoving]] + slow_ordered:
            # sort those samples which have this X coordinate first by increasing Y coordinate
            samplenames = sorted([s for s, p in positions.items() if p[slowestmoving] == slowpos],
                                 key=lambda s: positions[s][fastestmoving])
            if not samplenames:
                # no samples with this slow coordinate
                continue
            # see which end of the fastest coordinate is nearest to the last fast coordinate position
            if abs(positions[samplenames[-1]][fastestmoving] - lastfastcoord) < \
                    abs(positions[samplenames[0]][fastestmoving] - lastfastcoord):
                samplenames = reversed(samplenames)
            samplenames_ordered.extend(samplenames)
            lastfastcoord = positions[samplenames_ordered[-1]][fastestmoving]
        assert sorted([d.samplename for d in self._data]) == sorted(samplenames_ordered)
        self.beginResetModel()
        sorteddata = [[d for d in self._data if d.samplename == sn][0] for sn in samplenames_ordered]
        self._data = sorteddata
        self.endResetModel()
