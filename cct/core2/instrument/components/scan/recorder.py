import enum
import logging
import multiprocessing.pool
from typing import Optional, List, Tuple

import numpy as np
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from ..motors import Motor
from ....algorithms.beamweighting import beamweights
from ....dataclasses import Exposure
from ....devices.device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ScanRecorder(QtCore.QObject):
    """Recording scans:

    1. move motor to the starting position
    2. open the shutter
    3. expose the first image
    4. move to the next point
    5. expose the next image
    6. if this is not the last image to expose, go to 4.
    7. close the shutter
    8. move the motor back to where it was before the scan
    9. if there are no more images to be processed, finish the scan.

    When an error happens in the steps:
    1. (starting position cannot be reached) -> go to step 8.
    2. (shutter cannot be opened) -> go to step 8
    3. (exposure failed) -> go to step 7
    4. (next position cannot be reached) -> go to step 7
    5. (exposure failed) -> go to step 7
    6.
    7. (shutter cannot be closed) -> go to step 8
    8. (motor cannot go back) -> go to step 9
    9.

    Handling step #5 is somewhat tricky. The end of the exposure is signaled in two ways: a) an exposureFinished signal
    from the Exposer component or b) an imageReceived signal from the same. The order they arrive in is not defined.
    Only after both of them is received is the detector ready for another exposure. But just after either is received,
    the motor can be moved to the next point. With this consideration we can reduce dead time considerably.
    """

    class State(enum.Enum):
        Idle = 'idle'
        Initializing = 'Initializing'
        MoveToStart = 'Moving motor to start position'
        OpeningShutter = 'Opening beam shutter'
        ClosingShutter = 'Closing beam shutter'
        MotorMoving = 'Motor moving'
        MotorReset = 'Motor reset'
        Exposing = 'Exposing'
        Finishing = 'Finishing'
        StopRequested = 'Stop requested'
        WaitingForImages = 'Waiting for image processing'
        WaitingForDetector = 'Waiting for detector to become ready'

    scanindex: int
    startposition: float
    endposition: float
    nsteps: int
    countingtime: float
    imageprocessorpool: Optional[multiprocessing.pool.Pool] = None
    motor: Motor
    stepsexposed: int
    imagesdone: int
    positionsdone: List[float]
    state: State = State.Idle
    finished = Signal(bool, str)
    scanpoint = Signal(tuple)
    progress = Signal(float, float, float, str)
    initialmotorposition: float
    instrument: "Instrument"
    imageprocessingtasks: List[multiprocessing.pool.AsyncResult]
    movemotorback: bool = True
    errormessage: Optional[str] = None
    shutter: bool = True
    imageprocessingtimer: Optional[int] = None
    mask: Optional[np.ndarray] = None
    mask_total: Optional[np.ndarray] = None
    exposurefinished: bool = True
    imagesrequested: int = 0  # number of images we are waiting for

    def __init__(self, index: int, startposition: float, endposition: float, nsteps: int, countingtime: float,
                 motor: Motor, instrument: "Instrument", movemotorback: bool = True, shutter: bool = True):
        super().__init__()
        self.scanindex = index
        self.startposition = startposition
        self.endposition = endposition
        self.nsteps = nsteps
        self.motor = motor
        self.motor.stopped.connect(self.onMotorStopped)
        self.initialmotorposition = motor.where()
        self.state = self.state.Initializing
        self.instrument = instrument
        self.instrument.exposer.exposureFinished.connect(self.onExposureFinished)
        self.instrument.exposer.imageReceived.connect(self.onImageReceived)
        self.motor.moving.connect(self.onMotorMoving)
        self.imageprocessingtasks = []
        self.countingtime = countingtime
        self.movemotorback = movemotorback
        self.shutter = shutter
        if self.shutter:
            self.instrument.devicemanager.source().shutter.connect(self.onShutter)

    def openShutter(self):
        if self.shutter:
            self.state = self.State.OpeningShutter
            self.progress.emit(0, 0, 0, 'Opening shutter')
            try:
                self.instrument.devicemanager.source().moveShutter(True)
            except DeviceFrontend.DeviceError:
                self.onShutter(False)
        else:
            self.exposeNextImage()

    def closeShutter(self):
        if self.shutter:
            self.state = self.State.ClosingShutter
            self.progress.emit(0, 0, 0, 'Closing shutter')
            self.instrument.devicemanager.source().moveShutter(False)
        else:
            self.moveMotorBack()

    def moveMotorBack(self):
        if self.movemotorback:
            self.state = self.State.MotorReset
            try:
                self.motor.moveTo(self.initialmotorposition)
            except DeviceFrontend.DeviceError as de:
                self.errormessage = f'Error while moving motor back to start position: {de}'
                self.onMotorStopped(False, self.motor.where())
        else:
            self.waitForImageProcessing()

    def isReadyForExposure(self):
        return self.exposurefinished and (self.imagesrequested == 0)

    def exposeNextImage(self):
        """Start the next exposure"""
        if not self.isReadyForExposure():
            self.startTimer(10, QtCore.Qt.TimerType.PreciseTimer)
            logger.debug('Detector is not ready yet, cannot start exposure.')
            self.state = self.State.WaitingForDetector
            return
        else:
            logger.debug('Starting next exposure')
            self.positionsdone.append(self.motor.where())
            self.state = self.State.Exposing
            self.instrument.exposer.startExposure(self.instrument.config['path']['prefixes']['scn'], self.countingtime)
            self.imagesrequested += 1
            self.exposurefinished = False

    def moveToNextPosition(self):
        """Move the motor to the next scan position"""
        # do the next scan point
        self.stepsexposed += 1
        self.progress.emit(0, self.nsteps, self.stepsexposed, f'{self.stepsexposed}/{self.nsteps} done')
        if self.stepsexposed >= self.nsteps:
            logger.debug('Final point scanned.')
            self.closeShutter()
            return
        logger.debug('Moving to next position')
        position = self.startposition + (self.endposition - self.startposition) / (
                self.nsteps - 1) * self.stepsexposed
        self.state = self.State.MotorMoving
        try:
            self.motor.moveTo(position)
        except DeviceFrontend.DeviceError as de:
            self.onMotorStopped(False, self.motor.where())

    def waitForImageProcessing(self):
        if self.state == self.State.StopRequested:
            self.finalize()
        elif (self.imageprocessingtimer is None) and (self.imagesrequested == 0):
            assert not self.imageprocessingtasks
            self.finalize()
        else:
            self.state = self.State.WaitingForImages

    def start(self):
        if self.state != self.State.Initializing:
            raise RuntimeError('Cannot start: not in the initializing state.')
        self.stepsexposed = 0
        self.imagesdone = 0
        self.imagesrequested = 0
        self.positionsdone = []
        self.errormessage = None
        self.state = self.State.MoveToStart
        self.imageprocessingtasks = []
        assert self.imageprocessorpool is None
        assert self.imageprocessingtimer is None
        self.imageprocessorpool = multiprocessing.pool.Pool()
        self.exposurefinished = True
        try:
            self.motor.moveTo(self.startposition)
        except DeviceFrontend.DeviceError as de:
            self.onMotorStopped(False, self.motor.where())

    def stop(self):
        currentstate = self.state
        self.state = self.State.StopRequested
        if currentstate == self.State.Initializing:
            self.finalize()
        elif currentstate == self.State.MoveToStart:
            self.motor.stop()
        elif currentstate == self.State.MotorMoving:
            self.motor.stop()
        elif currentstate == self.State.MotorReset:
            self.motor.stop()
        elif currentstate == self.State.Exposing:
            self.instrument.exposer.stopExposure()
        elif currentstate == self.State.OpeningShutter:
            self.closeShutter()
        elif currentstate == self.State.ClosingShutter:
            pass
        else:
            assert False

    @Slot(bool)
    def onShutter(self, state: bool):
        if self.state == self.State.OpeningShutter:
            if state:
                self.exposeNextImage()
            else:
                # opening the shutter failed
                logger.error('Cannot open shutter')
                self.errormessage = 'Cannot open shutter.'
                self.moveMotorBack()
        elif self.state == self.State.ClosingShutter:
            if not state:
                self.moveMotorBack()
            else:
                # closing the shutter failed
                logger.error('Cannot close shutter')
                self.errormessage = 'Cannot close shutter.'
                self.moveMotorBack()
        elif self.state == self.State.StopRequested:
            self.waitForImageProcessing()
        else:
            # shutter opened or closed during the measurement. Do nothing, only issue a warning.
            logger.warning(f'Shutter {"opened" if state else "closed"} during the scan measurement.')

    @Slot(bool, float)
    def onMotorStopped(self, success: bool, endposition: float):
        logger.debug(f'Motor stopped {success=}, {endposition=}')
        if not success:
            expectedposition = self.startposition + (self.endposition - self.startposition) / (
                    self.nsteps - 1) * self.stepsexposed
            self.errormessage = f'Positioning error in scan {self.scanindex} at point {self.stepsexposed} in state {self.state.value}. We are at {endposition}, instead of the expected {expectedposition}'
            logger.error(self.errormessage)
            if self.state == self.State.MoveToStart:
                self.moveMotorBack()
            elif self.state == self.State.MotorMoving:
                self.closeShutter()
            elif self.state == self.State.MotorReset:
                self.waitForImageProcessing()
            elif self.state == self.State.StopRequested:
                self.waitForImageProcessing()
        else:
            # successful move
            if self.state == self.State.MoveToStart:
                self.openShutter()
            elif self.state == self.State.MotorMoving:
                self.exposeNextImage()
            elif self.state == self.State.MotorReset:
                self.waitForImageProcessing()
            elif self.state == self.State.StopRequested:
                self.waitForImageProcessing()

    @Slot(float, float, float)
    def onMotorMoving(self, current: float, start: float, end: float):
        if self.state in [self.State.MotorReset, self.State.MoveToStart]:
            self.progress.emit(start, end, current, self.state.value)
        else:
            pass

    @Slot(object)
    def onImageReceived(self, exposure: Exposure):
        logger.debug('Image received')
        assert self.imagesrequested > 0
        self.imagesrequested -= 1
        if self.imagesrequested > 1:
            logger.warning(f'More than one outstanding images: {self.imagesrequested}. '
                           f'Might be caused by jamming of subsequent exposures!')
        if self.mask is None:
            if self.instrument.config['scan']['mask'] is None:
                self.mask = exposure.intensity >= 0
            else:
                try:
                    self.mask = self.instrument.io.loadMask(self.instrument.config['scan']['mask'])
                except (KeyError, FileNotFoundError, TypeError):
                    self.mask = exposure.intensity >= 0
        if self.mask_total is None:
            if self.instrument.config['scan']['mask_total'] is None:
                self.mask_total = exposure.intensity >= 0
            else:
                try:
                    self.mask_total = self.instrument.io.loadMask(self.instrument.config['scan']['mask_total'])
                except (KeyError, FileNotFoundError, TypeError):
                    self.mask_total = exposure.intensity >= 0
        logger.debug('Queueing analyzeimage task to imageprocessorpool')
        self.imageprocessingtasks.append(
            self.imageprocessorpool.apply_async(self._analyzeimage, args=(exposure, self.mask, self.mask_total)))
        if self.imageprocessingtimer is None:
            self.imageprocessingtimer = self.startTimer(1, QtCore.Qt.TimerType.VeryCoarseTimer)
        if not self.exposurefinished:
            # imageReceived signal has been called first.
            logger.debug('imageReceived signal has been called first')
            self.moveToNextPosition()

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        if (self.state == self.State.WaitingForDetector):
            if self.isReadyForExposure():
                if timerEvent.timerId() != self.imageprocessingtimer:
                    self.killTimer(timerEvent.timerId())
                self.exposeNextImage()
                return
        # see if image processing has been finished
        if not self.imageprocessingtasks:
            self.killTimer(timerEvent.timerId())
            self.imageprocessingtimer = None
            if self.state == self.State.WaitingForImages:
                # exposures are done, only waiting for image processing
                self.finalize()
            return
        if self.imageprocessingtasks[0].ready():
            # wait until the first is ready: process images in sequence
            task = self.imageprocessingtasks.pop(0)
            position = self.positionsdone.pop(0)
            readings = task.get()
            self.imagesdone += 1
            logger.debug(
                f'New scan point: at {position=}. {self.imagesdone=}. {self.positionsdone=}, {len(self.imageprocessingtasks)=}')
            self.scanpoint.emit((position,) + tuple(readings))

    @Slot(bool)
    def onExposureFinished(self, success: bool):
        """Called when the detector signals that the exposure is finished.

        Either this or onImageReceived() will be called first.
        """
        logger.debug(f'Exposure finished: {success=}')
        self.exposurefinished = True
        if self.state == self.State.StopRequested:
            self.waitForImageProcessing()
        elif not success:
            self.errormessage = f'Exposure error in scan {self.scanindex} at point {self.stepsexposed} in state {self.state.value}'
            self.closeShutter()
        else:
            # successful exposure
            if (self.imagesrequested > 0):
                logger.debug('exposureFinished signal received first.')
                # exposureFinished signal has been emitted first.
                self.moveToNextPosition()

    @staticmethod
    def _analyzeimage(exposure: Exposure, mask: np.ndarray, mask_total: np.ndarray) -> Tuple:
        """Analyze the recorded image and calculate some statistics from it.

        This worker function is called in a separate thread, not to hog the main one.
        """
        img = exposure.intensity
        sumtotal, maxtotal, meanrowtotal, meancoltotal, sigmarowtotal, sigmacoltotal, pixelcount = beamweights(img,
                                                                                                               mask_total)
        summasked, maxmasked, meanrowmasked, meancolmasked, sigmarowmasked, sigmacolmasked, pixelcount = beamweights(
            img, mask)
        return (exposure.header.fsn, sumtotal, summasked, maxtotal, maxmasked, meanrowtotal, meanrowmasked,
                meancoltotal, meancolmasked,
                sigmarowtotal, sigmarowmasked, sigmacoltotal, sigmacolmasked,
                (sigmarowtotal ** 2 + sigmacoltotal ** 2) ** 0.5, (sigmarowmasked ** 2 + sigmacolmasked ** 2) ** 0.5)

    def finalize(self):
        self.imageprocessorpool.close()
        self.imageprocessorpool.join()
        self.imageprocessorpool = None
        if self.state != self.State.StopRequested:
            assert self.imageprocessingtimer is None
            assert not self.imageprocessingtasks
            assert self.imagesrequested == 0
        self.finished.emit(self.errormessage is None, self.errormessage if self.errormessage is not None else 'Success')
