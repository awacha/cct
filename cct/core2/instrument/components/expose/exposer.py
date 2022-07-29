import enum
import enum
import logging
import multiprocessing
import time
from typing import Dict, Optional, Any, List

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from .exposuredata import ExposureTask, ExposureState
from ..component import Component
from ..devicemanager import DeviceManager
from ....dataclasses import Exposure
from ....devices.detector.pilatus.backend import PilatusBackend
from ....devices.detector.pilatus.frontend import PilatusDetector

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ExposerState(enum.Enum):
    Idle = enum.auto()
    Preparing = enum.auto()
    Starting = enum.auto()
    Exposing = enum.auto()
    Stopping = enum.auto()


class Exposer(QtCore.QObject, Component):
    """Handle exposures.

    1. An exposure of one or multiple images is initiated by the startExposure() method, which:
        - assures that the detector is in an idle state, and no exposures have been initiated yet
        - connects signal handlers to the detector
        - create an ExposureTask instance for each exposed image: these will be responsible for the actual data
          collection
        - start preparing the detector for an exposure, i.e.:
            - set the exposure time
            - set the delay time between two frames
            - set the number of frames
            - set the image save path
        - after this, the startExposure() method returns with the file sequence number of the first exposure to be made.

    2. When preparing the detector is finished (the detector device notifies us via a signal, to which the handler has
       already been connected in startExposure()), the detector is instructed to start the exposure.

    3. When the detector replies that the exposure has been started, notify the ExposureTask instances of this fact, so
       they can start acquiring data when it is their time. The start and end of acquisition is estimated from the start
       time, the exposure times and delay times, because there is no way to get this information from the detector (the
       Pilatus detector is unresponsive while doing data acquisition)

    4. Each ExposureTask notifies the Exposer object through the exposurestarted and exposureended signals when their
       time has come and went. If the exposure is stopped (user request, sudden unexpected TCP/IP communication error
       with the detector computer or a panic situation), these may not be emitted at all.

    5. After the exposure time has elapsed, the ExposureTask starts looking for the image file on the disk / network
       share. If found in a given interval (e.g. 2 seconds after the estimated end of the exposure), a metadata file
       (pickle) is written, the image is loaded and an Exposure object is constructed, and returned to the Exposer via
       the `finished` signal. If the waiting for the image times out, or the exposure has been stopped for some reason
       (see above), None is returned instead of the Exposure object via the `finished` signal. The last signal emitted
       by the ExposureTask is `finished`. It has two parameters: a bool (success or failure) and the Exposure object
       (or None if the exposure failed for some reason). After it is emitted, the ExposureTask is removed.

    6. The Exposer becomes idle when the detector becomes idle after the exposure AND all ExposureTasks have emitted
       their `exposureended` signals. At this time some ExposureTasks might still be waiting for the image file to
       become available in the file system, but this doesn't mean that a new exposure cannot be started.

    To the outside, interfacing with the Exposer is sufficient. This can be done with the following signals and methods:

    Signals:
        exposureFinished(bool): The previous exposure is done (successfully or not), another one can be started.
        exposureStarted(): An exposure has been requested, no more exposure can be started until the exposureFinished
            signal is emitted
        exposureProgress(prefix: str, fsn: int, currenttime: float, starttime: float, endtime: float):
            this signal is emitted periodically with the following parameters:
                prefix: the file name prefix of the currently exposed image
                fsn: the file sequence number of the currently exposed image
                currenttime: timestamp (time.monotonic()) when the signal is emitted
                starttime: timestamp (time.monotonic()) of the (estimated) start of the exposure of the current image
                endtime: timestamp (time.monotonic()) of the (estimated) end of the exposure of the current image
        imageReceived(Exposure): an image has been received.

    Methods:
         startExposure(...): request exposing one or more images
         stopExposure(): stop the currently running exposure
    """
    ## Signals
    exposureFinished = Signal(bool)  # bool = success or failure
    exposureProgress = Signal(str, int, float, float,
                              float)  # prefix, fsn currently exposed, currenttime, starttime, endtime
    imageReceived = Signal(object)
    exposureStarted = Signal()

    # List of ongoing exposure tasks
    exposuretasks: List[ExposureTask]
    detector: Optional[PilatusDetector] = None
    state: ExposerState = ExposerState.Idle
    lastheaderdata: Dict[str, Any]
    progressinterval: float = 0.5
    progresstimer: Optional[int] = None
    firstfilename: Optional[str] = None
    currentexposure: Optional[ExposureTask] = None

    def __init__(self, **kwargs):
        self.state = ExposerState.Idle
        self.exposuretasks = []
        super().__init__(**kwargs)

    def _connectDetector(self):
        """Connect signals to the Detector instance"""
        if self.detector is not None:
            logger.warning('Detector signals already connected')
            return
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
            logger.warning('Emitting exposureFinished only because disconnecting the detector while exposing.')
            self.state = ExposerState.Idle
            self.exposureFinished.emit(False)
        self.detector.connectionEnded.disconnect(self.onDetectorDisconnected)
        self.detector.variableChanged.disconnect(self.onDetectorVariableChanged)
        self.detector.commandResult.disconnect(self.onCommandResult)
        self.detector = None

    def startExposure(self, prefix: str, exposuretime: float, imagecount: int = 1, delay: float = 0.003,
                      maskoverride: Optional[str] = None, writenexus: bool = True) -> int:
        """prepare the detector for an exposure. Also prepare timers for waiting for images.

        :param prefix: file name prefix (e.g. 'crd', 'tst', 'scn' etc.)
        :type prefix: str
        :param exposuretime: duration of a single exposure (sec)
        :type exposuretime: float
        :param imagecount: number of exposures to be done
        :type imagecount: int
        :param delay: delay between exposures (sec). Should be long enonugh to cover the detector read-out time.
        :type delay: float
        :param maskoverride: use a different mask for this exposure
        :type maskoverride: str (file name)
        :param writenexus: write the results to a NeXus HDF5 file conforming the NXsas application definition
        :type writenexus: bool
        :return: the next available file sequence number
        :rtype: int
        """
        # first check if we are in a panic state: if yes, refuse starting an exposure
        if self._panicking != self.PanicState.NoPanic:
            raise RuntimeError('Cannot start exposure: panic!')
        # check if an exposure is already running
        if self.state != ExposerState.Idle:
            raise RuntimeError('Cannot start exposure: another exposure is already running.')
        # connect the detector signal handlers
        if self.detector is None:
            self._connectDetector()
        # check if the detector is idle
        if self.detector['__status__'] != PilatusBackend.Status.Idle:  # e.g. the detector is trimming
            self._disconnectDetector()
            raise RuntimeError(
                f'Cannot start exposure: the detector is not idle (instead {self.detector["__status__"]}).')
        # Prepare the exposure (but do not start it yet)!

        # ##############################################
        # state: Idle -> Preparing
        # ##############################################

        self.state = ExposerState.Preparing
        nextfsn = self.instrument.io.nextfsn(prefix, checkout=imagecount)
        self.firstfilename = self.instrument.io.formatFileName(prefix, nextfsn, '.cbf')
        self.detector.prepareexposure(
            prefix,
            exposuretime, imagecount, delay
        )
        for i in range(imagecount):
            task = ExposureTask(
                self.instrument, self.detector, prefix, nextfsn + i, i, exposuretime, delay, maskoverride, writenexus)
            self.exposuretasks.append(task)
            task.exposurestarted.connect(self.onExposureTaskStarted)
            task.exposureended.connect(self.onExposureTaskEnded)
            task.finished.connect(self.onExposureTaskFinished)
        self.currentexposure = None
        try:
            self.exposureStarted.emit()
        except Exception as exc:
            logger.warning(f'Exception while emitting the exposureStarted() signal: {exc}')
        return nextfsn

    @Slot()
    def onExposureTaskStarted(self):
        self.currentexposure = self.sender()

    @Slot()
    def onExposureTaskEnded(self):
        if self.currentexposure is self.sender():
            self.currentexposure = None
        else:
            logger.warning(f'Current exposure task (fsn={self.currentexposure.fsn}'
                           f' is not the sender of the exposureended signal (fsn={self.sender().fsn})!')

    @Slot(bool, object)
    def onExposureTaskFinished(self, success: bool, exposure: Optional[Exposure]):
        if success and (exposure is not None):
            try:
                self.imageReceived.emit(exposure)
            except Exception as exc:
                logger.error(f'Exception while emitting imageReceived signal: {exc}.')
        self.exposuretasks.remove(self.sender())

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        if timerEvent.timerId() == self.progresstimer:
            if self.currentexposure is None:
                return
            self.exposureProgress.emit(
                self.currentexposure.prefix, self.currentexposure.fsn,
                time.monotonic(), self.currentexposure.starttime, self.currentexposure.endtime)

    def isExposing(self) -> bool:
        return self.state != ExposerState.Idle

    # ---------------------------------------------------------------------------------------------------------------
    # The following two functions (onCommandResult and onDetectorVariableChanged) are responsible for getting replies
    # from the detector hardware and ensure to change the state of the Exposer accordingly
    # ---------------------------------------------------------------------------------------------------------------

    @Slot(bool, str, str)
    def onCommandResult(self, success: bool, commandname: str, result: str):
        logger.debug(f'onCommandResult: {success}, {commandname}')
        if commandname == 'prepareexposure' and success:
            # the exposure has been successfully prepared.
            if self.state != ExposerState.Preparing:
                logger.warning('Detector reported the end of a prepareexposure command, but the exposer is not in the '
                               'Preparing state')
                return
            # ##############################################
            # state: Preparing -> Starting
            # ##############################################
            self.detector.exposeprepared(self.firstfilename)
            self.state = ExposerState.Starting
        elif commandname == 'expose' and success:
            if self.state != ExposerState.Starting:
                logger.warning('Detector reported the end of an exposure request command, but the exposer is not in the'
                               ' Starting state')
                return
            # ##############################################
            # state: Starting -> Exposing
            # ##############################################
            assert self.detector['__state__'] in [PilatusBackend.Status.Exposing, PilatusBackend.Status.ExposingMulti]
            self.state = ExposerState.Exposing

            # now start the timers of the ExposureTasks
            for task in self.exposuretasks:
                if task.status == ExposureState.Initializing:
                    task.onDetectorExposureStarted(self.detector.currentMessage.timestamp)

            # also start the timer for emitting the progress signal periodically
            self.progresstimer = self.startTimer(int(1000 * self.progressinterval), QtCore.Qt.CoarseTimer)

        elif commandname == 'expose' and (not success):
            if self.state != ExposerState.Starting:
                logger.warning('Detector reported the fail of an exposure request command, but the exposer is not in'
                               'the Starting state')
                return
            # ##############################################
            # state: Starting -> Idle
            # ##############################################

            logger.error(f'Error while starting exposure: {result}')
            # remove to-be-started tasks
            self.exposuretasks = [t for t in self.exposuretasks if t.status != ExposureState.Initializing]
            if n := [t for t in self.exposuretasks if t.status in [ExposureState.Running, ExposureState.Pending]]:
                logger.error(
                    f'There are still {n} exposure tasks Running/Pending. There shouldn\'t be any at this point!')
            self.state = ExposerState.Idle  # we won't get __state__ change from the detector to set this
            # Emit the exposureStarted and exposureFinished signals quickly after each other.
            self.exposureStarted.emit()
            self.exposureFinished.emit(False)
        elif commandname == 'stopexposure' and success:
            if self.state != [ExposerState.Exposing, ExposerState.Starting]:
                logger.warning('Detector reported the end of a stop request command, but the exposer is not in the'
                               ' Starting or Exposing states')
            logger.error(f'Exposure stop requested by user.')
            self.state = ExposerState.Stopping
        elif commandname == 'stopexposure' and (not success):
            logger.error(f'Exposure cannot be stopped: {result}')
        else:
            pass

    @Slot(str, object, object)
    def onDetectorVariableChanged(self, variable: str, value: Any, prevvalue: Any):
        if (variable == '__status__') and (self.state in [ExposerState.Exposing, ExposerState.Stopping]) and (
                value in [PilatusBackend.Status.Idle]):
            # this means that exposing is done without error. Images are not necessarily read yet.
            # ##############################################
            # state: Exposing/Stopping -> Idle
            # ##############################################

            externalstop = self.state == ExposerState.Stopping
            logger.debug('Exposure stopped.' if externalstop else 'Exposure finished.')
            self.state = ExposerState.Idle
            self.exposureFinished.emit(not externalstop)
            self.killTimer(self.progresstimer)
            self.progresstimer = None
            # check if the stopping was due to a panic event
            if self._panicking == self.PanicState.Panicking:
                super().panichandler()

    @Slot()
    def onDetectorDisconnected(self):
        self._disconnectDetector()

    @Slot()
    def stopExposure(self):
        self.instrument.devicemanager.detector().stopexposure()

    def isIdle(self) -> bool:
        return self.state == ExposerState.Idle

    def imagesPending(self) -> int:
        return len([et for et in self.exposuretasks])

    def panichandler(self):
        """Handle a panic-shutdown request

        When a panic event occurs:
            - if idle, acknowledge the panic at once
            - if not idle, stop the exposure and only acknowledge the panic if the exposure has ended.
        """
        self._panicking = self.PanicState.Panicking
        if self.state == ExposerState.Idle:
            super().panichandler()
        elif self.state == ExposerState.Stopping:
            # already stopping
            pass
        else:
            self.stopExposure()
