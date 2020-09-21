import datetime
import enum
import logging
import os
import pickle
import time
import multiprocessing
from typing import Dict, Optional, Any, List

from PyQt5 import QtCore
import numpy as np

from .component import Component
from .devicemanager import DeviceManager
from .io import IO
from ...dataclasses import Header, Exposure
from ...devices.detector.pilatus.backend import PilatusBackend
from ...devices.detector.pilatus.frontend import PilatusDetector

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ExposerState(enum.Enum):
    Idle = enum.auto()
    Starting = enum.auto()
    Exposing = enum.auto()
    Stopping = enum.auto()


class ExposureData:
    # all times are from time.monotonic()
    prefix: str
    fsn: int
    command_issue_time: Optional[float] = None  # when the expose command was issued to the detector backend process
    command_ack_time: Optional[float] = None  # when the detector backend process replied to the expose command
    exptime: float  # exposure time
    expdelay: float  # delay between exposures
    imagetimeout: float = 2  # timeout for waiting for the image.
    index: int  # 0-based index of this image in a multiple exposure sequence

    def __init__(self, prefix: str, fsn: int, index: int, exptime: float, expdelay: float, cmdissuetime: float):
        self.prefix = prefix
        self.fsn = fsn
        self.index = index
        self.exptime = exptime
        self.expdelay = expdelay
        self.exptime = exptime
        self.command_issue_time = cmdissuetime

    def isTimedOut(self) -> bool:
        return time.monotonic() > self.endtime + self.imagetimeout

    @property
    def starttime(self):
        """expected start time of this image"""
        return self.command_ack_time + self.index * (self.exptime + self.expdelay)

    @property
    def endtime(self):
        """expected end time of this image"""
        return self.starttime + self.exptime

    def currentlyExposing(self) -> bool:
        now = time.monotonic()
        return (self.starttime <= now) and (self.endtime > now)


class Exposer(QtCore.QObject, Component):
    """Handle exposures.

    This component of the Instrument has the following tasks:
        - start exposures
        - wait for images (even after an exposure is done)
        - construct and write header data

    An exposure sequence has the following steps:
        - initializing the detector (issuing the 'expose' command)
        - waiting for an acknowledgement of the 'expose' command from the detector
        - when the 'expose' command is acknowledged, start timer(s) which will wait for the image(s).
        - when the detector signals that it is finished (state -> Idle): another exposure can be started
        - note that when a detector is finished, there may still be outstanding images due to network lag.

    Either single or multi-exposure, images are waited for. Timers are stored in the `waittimers` attribute, which is
    a dictionary of int or float keys
        - float keys correspond to unstarted timers
        - int keys are QTimer IDs
    The values of the dict are tuples of file prefix (str), file sequence number (int), expected end time (float, in
    units of time.monotonic()).

    When an exposure sequence starts, float keys are generated. They are turned into int keys when the acknowledgement
    of the 'expose' command is received.
    """
    exposureFinished = QtCore.pyqtSignal(bool)  # bool = success or failure
    exposureProgress = QtCore.pyqtSignal(str, int, float, float,
                                         float)  # prefix, fsn currently exposed, currenttime, starttime, endtime
    imageReceived = QtCore.pyqtSignal(object)
    exposureStarted = QtCore.pyqtSignal()
    waittimers: Dict[int, ExposureData]
    pendingtimers: List[ExposureData]
    detector: Optional[PilatusDetector] = None
    state: ExposerState = ExposerState.Idle
    lastheaderdata: Dict[str, Any]
    progressinterval: float = 0.5
    progresstimer: Optional[int] = None
    datareductionpipeline: multiprocessing.Process = None
    datareduction_commandqueue: multiprocessing.Queue = None
    datareduction_resultqueue: multiprocessing.Queue = None

    def __init__(self, **kwargs):
        self.waittimers = {}
        self.pendingtimers = []
        self.state = ExposerState.Idle
        super().__init__(**kwargs)

    def _connectDetector(self):
        """Connect signals to the Detector instance"""
        assert self.detector is None
        assert isinstance(self.instrument.devicemanager, DeviceManager)
        detector = self.instrument.devicemanager.detector()
        assert isinstance(detector, PilatusDetector)  # ToDo: generalize
        self.detector = detector
        self.detector.connectionEnded.connect(self.onDetectorDisconnected)
        self.detector.variableChanged.connect(self.onDetectorVariableChanged)
        self.detector.commandResult.connect(self.onCommandResult)

    def _disconnectDetector(self):
        """Disconnect signal handlers from the Detector instance"""
        if self.isExposing():
            self.cleanupExposure()
            self.exposureFailed.emit()
        self.detector.connectionEnded.disconnect(self.onDetectorDisconnected)
        self.detector.variableChanged.disconnect(self.onDetectorVariableChanged)
        self.detector = None

    def startExposure(self, prefix: str, exposuretime: float, imagecount: int = 1, delay: float = 0.003):
        """prepare the detector for an exposure. Also prepare timers for waiting for images."""
        if self.detector is None:
            self._connectDetector()
        if ((self.state != ExposerState.Idle) or  # e.g. we are waiting for the acknowledgement of the start command
                (self.detector['__status__'] != PilatusBackend.Status.Idle)):  # e.g. the detector is trimming
            raise RuntimeError(
                f'Cannot start exposure: the detector is not idle (instead {self.detector["__status__"]}).')
        io = self.instrument.io
        assert isinstance(io, IO)
        nextfsn = io.nextfsn(prefix, checkout=imagecount)
        # start the exposure
        firstfilename = io.formatFileName(prefix, nextfsn, '.cbf')
        logger.debug(f'Starting exposure: {prefix=}, {firstfilename=}, {exposuretime=}, {imagecount=}, {delay=}')
        self.detector.expose(
            prefix,
            firstfilename,
            exposuretime, imagecount, delay
        )
        cmdissuetime = time.monotonic()
        self.state = ExposerState.Starting
        # initialize timers.
        for i in range(imagecount):
            # do not initialize the timers yet.
            self.pendingtimers.append(ExposureData(
                prefix, i + nextfsn, i, exposuretime, delay, cmdissuetime))

    def _currentlyExposedImage(self) -> Optional[ExposureData]:
        try:
            return [v for v in self.waittimers.values() if v.currentlyExposing()][0]
        except IndexError:
            return None

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        if timerEvent.timerId() == self.progresstimer:
            logger.debug('progress timer')
            expdata = self._currentlyExposedImage()
            if expdata is not None:
                logger.debug(f'Currently exposed image: {expdata.prefix=}, {expdata.fsn=}')
                self.exposureProgress.emit(
                    expdata.prefix, expdata.fsn, time.monotonic(), expdata.starttime, expdata.endtime)
            return
        # the time has arrived to check for an image.
        self.killTimer(timerEvent.timerId())
        expdata = self.waittimers[timerEvent.timerId()]
        # see if the file is available
        try:
            logger.debug(f'Checking for image {expdata.prefix=}, {expdata.fsn=}')
            image = self.instrument.io.loadCBF(expdata.prefix, expdata.fsn, check_local=False)
        except FileNotFoundError:
            if expdata.isTimedOut():
                # timed out
                logger.error(f'Timeout while waiting for CBF file {expdata.prefix=}, {expdata.fsn=}')
                del self.waittimers[timerEvent.timerId()]
                return
            else:
                # no timeout, requeue
                self.waittimers[self.startTimer(0, QtCore.Qt.VeryCoarseTimer)] = expdata
                logger.debug(f'Waiting more for image {expdata.prefix=}, {expdata.fsn=}')
                return
        else:
            # we have the image. Construct a header and load the required mask.
            header = self.createHeader(expdata.prefix, expdata.fsn, expdata.exptime, expdata.starttime)
            try:
                mask = self.instrument.io.loadMask(header.maskname)
            except FileNotFoundError:
                logger.warning(f'Invalid mask file "{header.maskname}". You might have to create a mask yourself.')
                mask = np.ones_like(image, dtype=np.uint8)
            uncertainty = image ** 0.5
            uncertainty[image <= 0] = 1
            # emit the raw image.
            exposure = Exposure(image, header, uncertainty, mask)
            if expdata.prefix == self.config['path']['prefixes']['crd']:
                self.instrument.datareduction.submit(exposure)
            self.imageReceived.emit(exposure)
            logger.debug(f'Image received for {expdata.prefix=}, {expdata.fsn=}')
            # remove the timer
            del self.waittimers[timerEvent.timerId()]

    def isExposing(self) -> bool:
        return self.state != ExposerState.Idle

    def onDetectorVariableChanged(self, variable: str, value: Any):
        # logger.debug(f'Detector variable changed: {variable=}, {value=}')
        if variable == '__status__':
            logger.debug(f'Detector status changed to {value}')
            if (self.state == ExposerState.Starting) and (
                    value in [PilatusBackend.Status.Exposing, PilatusBackend.Status.ExposingMulti]):
                # acknowledgement for the exposure command
                self.state = ExposerState.Exposing
                self.progresstimer = self.startTimer(int(1000 * self.progressinterval), QtCore.Qt.CoarseTimer)
            elif (self.state == ExposerState.Exposing) and (value in [PilatusBackend.Status.Idle]):
                # this means that exposing is done. Images are not necessarily read yet.
                self.state = ExposerState.Idle
                self.exposureFinished.emit(True)
                self.killTimer(self.progresstimer)
                self.progresstimer = None
            elif (self.state == ExposerState.Stopping) and (value in [PilatusBackend.Status.Idle]):
                # this means that an user stop request has been fulfilled.
                self.state = ExposerState.Idle
                self.exposureFailed.emit()
                self.killTimer(self.progresstimer)
                self.progresstimer = None

    def onDetectorDisconnected(self):
        self._disconnectDetector()

    def stopExposure(self):
        self.instrument.devicemanager.detector().stopexposure()

    def createHeader(self, prefix: str, fsn: int, exptime: float, starttime: float) -> Header:
        sample = self.instrument.samplestore.currentSample()
        data = {
            'fsn': fsn,
            'filename': os.path.abspath(
                os.path.join(
                    self.config['path']['directories']['param'], prefix,
                    self.instrument.io.formatFileName(prefix, fsn, '.pickle'))),
            'exposure': {
                'fsn': fsn,
                'prefix': prefix,
                'exptime': exptime,
                'monitor': exptime,
                'startdate': datetime.datetime.fromtimestamp(time.time() - time.monotonic() + starttime),
                'date': datetime.datetime.now(),
                'enddate': datetime.datetime.now(),
            },
            'geometry': self.instrument.geometry.currentpreset.getHeaderEntry(),
            'sample': sample.toDict() if sample is not None else {},
            'motors': self.instrument.motors.getHeaderEntry(),
            'devices': {dev.devicename: dev.toDict() for dev in self.instrument.devicemanager},
            'environment': {},
            'accounting': {'projectid': self.instrument.projects.project().projectid,
                           'operator': self.instrument.auth.username(),
                           'projectname': self.instrument.projects.project().title,
                           'proposer': self.instrument.projects.project().proposer},
        }
        # environment
        try:
            vac = self.instrument.devicemanager.vacuum()
            data['environment']['vacuum_pressure'] = vac.pressure()
        except KeyError:
            pass
        try:
            temp = self.instrument.devicemanager.temperature()
            data['environment']['temperature'] = temp.temperature()
        except KeyError:
            pass
        # adjust truedistance
        if sample is not None:
            data['geometry']['truedistance'] = data['geometry']['dist_sample_det'] - data['sample']['distminus.val']
            data['geometry']['truedistance.err'] = (data['geometry']['dist_sample_det.err'] ** 2 + data['sample'][
                'distminus.err'] ** 2) ** 0.5
        folder, filename = os.path.split(data['filename'])
        os.makedirs(folder, exist_ok=True)
        with open(data['filename'], 'wb') as f:
            pickle.dump(data, f)
        # check if we have a mask
        return Header(datadict=data)

    def onCommandResult(self, success: bool, commandname: str, result: str):
        if commandname == 'expose' and success:
            # now start the timers
            cmdacktime = self.detector.currentMessage.timestamp
            for expdata in self.pendingtimers:
                expdata.command_ack_time = cmdacktime
                self.waittimers[
                    self.startTimer(int(1000 * (expdata.endtime - time.monotonic())), QtCore.Qt.PreciseTimer)] = expdata
            self.pendingtimers = []
            self.exposureStarted.emit()
        elif commandname == 'expose' and (not success):
            logger.error(f'Error while starting exposure: {result}')
            # remove to-be-started timers.
            self.pendingtimers = []
            self.state = ExposerState.Idle  # we won't get __state__ change from the detector to set this
            self.exposureStarted.emit()
            self.exposureFinished.emit(False)
        elif commandname == 'stopexposure' and success:
            logger.error(f'Exposure stop requested by user.')
            assert self.state == ExposerState.Exposing
            self.state = ExposerState.Stopping
        elif commandname == 'stopexposure' and (not success):
            logger.error(f'Exposure cannot be stopped: {result}')
        else:
            pass

    def isIdle(self) -> bool:
        return self.state == ExposerState.Idle