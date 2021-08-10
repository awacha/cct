import enum
import logging
import multiprocessing.pool
from typing import Optional, List, Tuple

import numpy as np
from PyQt5 import QtCore

from ..motors import Motor
from ....algorithms.beamweighting import beamweights
from ....dataclasses import Scan, Exposure

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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

    scanindex: int
    startposition: float
    endposition: float
    nsteps: int
    countingtime: float
    imageprocessorpool: Optional[multiprocessing.pool.Pool] = None
    motor: Motor
    stepsexposed: int
    imagesdone: int
    receiving_images: int=0
    positionsdone: List[float]
    state: State = State.Idle
    finished = QtCore.pyqtSignal(bool, str)
    scanpoint = QtCore.pyqtSignal(tuple)
    progress = QtCore.pyqtSignal(float, float, float, str)
    initialmotorposition: float
    instrument: "Instrument"
    imageprocessingtasks: List[multiprocessing.pool.AsyncResult]
    movemotorback: bool = True
    errormessage: Optional[str] = None
    shutter: bool=True
    imageprocessingtimer: Optional[int]=None
    mask: Optional[np.ndarray] = None
    mask_total: Optional[np.ndarray] = None

    def __init__(self, index: int, startposition: float, endposition: float, nsteps: int, countingtime: float,
                 motor: Motor, instrument: "Instrument", movemotorback: bool = True, shutter: bool=True):
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
        self.imageprocessingtasks=[]
        self.countingtime = countingtime
        self.movemotorback = movemotorback
        self.shutter = shutter
        if self.shutter:
            self.instrument.devicemanager.source().shutter.connect(self.onShutter)

    def openShutter(self):
        if self.shutter:
            self.state = self.State.OpeningShutter
            self.progress.emit(0,0,0,'Opening shutter')
            self.instrument.devicemanager.source().moveShutter(True)
        else:
            self.exposeNextImage()

    def closeShutter(self):
        if self.shutter:
            self.state = self.State.ClosingShutter
            self.progress.emit(0,0,0,'Closing shutter')
            self.instrument.devicemanager.source().moveShutter(False)
        else:
            self.moveMotorBack()

    def moveMotorBack(self):
        if self.movemotorback:
            self.state = self.State.MotorReset
            self.motor.moveTo(self.initialmotorposition)
        else:
            self.waitForImageProcessing()

    def exposeNextImage(self):
        self.positionsdone.append(self.motor.where())
        self.state = self.State.Exposing
        self.instrument.exposer.startExposure(self.instrument.config['path']['prefixes']['scn'], self.countingtime)

    def moveToNextPosition(self):
        # do the next scan point
        assert self.stepsexposed < self.nsteps  # the last step should be detected before calling this method
        position = self.startposition + (self.endposition - self.startposition) / (
                self.nsteps - 1) * self.stepsexposed
        self.state = self.State.MotorMoving
        self.motor.moveTo(position)

    def waitForImageProcessing(self):
        if self.state == self.State.StopRequested:
            self.finalize()
        elif (self.imageprocessingtimer is None) and (self.receiving_images == 0):
            assert not self.imageprocessingtasks
            self.finalize()
        else:
            self.state = self.State.WaitingForImages

    def start(self):
        if self.state != self.State.Initializing:
            raise RuntimeError('Cannot start: not in the initializing state.')
        self.stepsexposed = 0
        self.imagesdone = 0
        self.receiving_images = 0
        self.positionsdone = []
        self.errormessage = None
        self.state = self.State.MoveToStart
        self.imageprocessingtasks = []
        assert self.imageprocessorpool is None
        assert self.imageprocessingtimer is None
        self.imageprocessorpool = multiprocessing.pool.Pool()
        self.motor.moveTo(self.startposition)

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
                self.errormessage= 'Cannot close shutter.'
                self.moveMotorBack()
        elif self.state == self.State.StopRequested:
            self.waitForImageProcessing()
        else:
            # shutter opened or closed during the measurement. Do nothing, only issue a warning.
            logger.warning(f'Shutter {"opened" if state else "closed"} during the scan measurement.')

    def onMotorStopped(self, success: bool, endposition: float):
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

    def onMotorMoving(self, current:float, start:float, end:float):
        if self.state in [self.State.MotorReset, self.State.MoveToStart]:
            self.progress.emit(start, end, current, self.state.value)
        else:
            pass

    def onImageReceived(self, exposure: Exposure):
        self.receiving_images -= 1  # this can be negative if the exposure finished signal comes after the image received signal.
        if self.receiving_images > 1:
            logger.warning(f'{self.receiving_images=}')
        if self.mask is None:
            try:
                self.mask = self.instrument.io.loadMask(self.instrument.config['scan']['mask'])
            except (KeyError, FileNotFoundError):
                self.mask = exposure.intensity>=0
        if self.mask_total is None:
            try:
                self.mask_total = self.instrument.io.loadMask(self.instrument.config['scan']['mask_total'])
            except (KeyError, FileNotFoundError):
                self.mask_total = exposure.intensity>=0
        self.imageprocessingtasks.append(self.imageprocessorpool.apply_async(self._analyzeimage, args=(exposure, self.mask, self.mask_total)))
        if self.imageprocessingtimer is None:
            self.imageprocessingtimer = self.startTimer(0, QtCore.Qt.VeryCoarseTimer)

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
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
            self.scanpoint.emit((position,)+tuple(readings))

    def onExposureFinished(self, success: bool):
        if self.state == self.State.StopRequested:
            self.waitForImageProcessing()
        elif not success:
            self.errormessage = f'Exposure error in scan {self.scanindex} at point {self.stepsexposed} in state {self.state.value}'
            self.closeShutter()
        else:
            # successful exposure
            self.receiving_images += 1
            self.stepsexposed += 1
            self.progress.emit(0, self.nsteps, self.stepsexposed, f'{self.stepsexposed}/{self.nsteps} done')
            if self.stepsexposed >= self.nsteps:
                self.closeShutter()
            else:
                self.moveToNextPosition()

    @staticmethod
    def _analyzeimage(exposure: Exposure, mask: np.ndarray, mask_total: np.ndarray) -> Tuple:
        img = exposure.intensity
        sumtotal, maxtotal, meanrowtotal, meancoltotal, sigmarowtotal, sigmacoltotal, pixelcount = beamweights(img, mask_total)
        summasked, maxmasked, meanrowmasked, meancolmasked, sigmarowmasked, sigmacolmasked, pixelcount = beamweights(img, mask)
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
            assert self.receiving_images == 0
        self.finished.emit(self.errormessage is None, self.errormessage if self.errormessage is not None else 'Success')
