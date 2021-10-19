from typing import Optional
import logging

from .command import Command
from .commandargument import StringArgument, FloatArgument, IntArgument
from ..dataclasses import Exposure
from ..devices.detector import PilatusDetector

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Expose(Command):
    name = 'expose'
    description = 'Make an exposure with the detector'
    arguments = [FloatArgument('exptime', 'Exposure time in seconds'),
                 StringArgument('prefix', 'Exposure prefix', defaultvalue='crd')]
    timerinterval = None
    success: Optional[bool] = None
    waiting_for_images: int = 0

    def connectExposer(self):
        self.instrument.exposer.exposureProgress.connect(self.onExposureProgress)
        self.instrument.exposer.imageReceived.connect(self.onImageReceived)
        self.instrument.exposer.exposureFinished.connect(self.onExposureFinished)

    def disconnectExposer(self):
        self.instrument.exposer.exposureProgress.disconnect(self.onExposureProgress)
        self.instrument.exposer.imageReceived.disconnect(self.onImageReceived)
        self.instrument.exposer.exposureFinished.disconnect(self.onExposureFinished)

    def onExposureProgress(self, prefix: str, fsn: int, currenttime: float, starttime: float, endtime: float):
        self.progress.emit(f'Exposing {prefix}/{fsn}, remaining time {endtime - currenttime:.1f} sec',
                           int(1000 * (currenttime - starttime) / (endtime - starttime)), 1000)

    def onExposureFinished(self, success: bool):
        self.success = success
        if not success:
            self.waiting_for_images = 0
        self.tryToFinalize()

    def tryToFinalize(self):
        if self.success is None:
            logger.debug('Cannot finalize: exposure not yet finished')
            return
        if self.waiting_for_images > 0:
            logger.debug(f'Cannot finalize: waiting for {self.waiting_for_images} images')
            return
        logger.debug('Finalizing: exposure finished and all images received.')
        self.disconnectExposer()
        if self.success:
            self.finish(True)
        else:
            self.fail('Error while exposing')

    def onImageReceived(self, exposure: Exposure):
        self.waiting_for_images -= 1
        self.tryToFinalize()

    def initialize(self, exptime: float, prefix: str):
        self.connectExposer()
        self.success = None
        self.waiting_for_images = 1
        try:
            fsn = self.instrument.exposer.startExposure(prefix, exptime)
        except:
            self.disconnectExposer()
            raise
        currentsample = self.instrument.samplestore.currentSample()
        self.message.emit(f'Started exposure crd/{fsn} (' + (
            f'sample {currentsample.title}' if currentsample is not None else 'no sample'
        ))

    def stop(self):
        self.instrument.exposer.stopExposure()


class ExposeMulti(Expose):
    name = 'exposemulti'
    description = 'Expose multiple images'
    arguments = [FloatArgument('exptime', 'Exposure time in seconds'),
                 IntArgument('nimages', 'Number of images'),
                 StringArgument('prefix', 'Exposure prefix', defaultvalue='crd'),
                 FloatArgument('delay', 'Delay between exposures in seconds', defaultvalue=0.003)]

    def initialize(self, exptime: float, nimages: int, prefix: str, delay: float):
        self.connectExposer()
        self.success = None
        self.waiting_for_images = nimages
        try:
            fsn = self.instrument.exposer.startExposure(prefix, exptime, nimages, delay)
        except:
            self.disconnectExposer()
            raise
        currentsample = self.instrument.samplestore.currentSample()
        self.message.emit(f'Started exposure crd/{fsn}...{fsn+nimages-1} (' + (
            f'sample {currentsample.title}' if currentsample is not None else 'no sample'
        ))
