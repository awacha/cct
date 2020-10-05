from .command import Command
from .commandargument import StringArgument, FloatArgument, IntArgument
from ..devices.detector import PilatusDetector


class Expose(Command):
    name = 'expose'
    description = 'Make an exposure with the detector'
    arguments = [FloatArgument('exptime', 'Exposure time in seconds'),
                 StringArgument('prefix', 'Exposure prefix', defaultvalue='crd')]

    def connectExposer(self):
        self.instrument.exposer.exposureProgress.connect(self.onExposureProgress)
        self.instrument.exposer.exposureFinished.connect(self.onExposureFinished)

    def disconnectExposer(self):
        self.instrument.exposer.exposureProgress.disconnect(self.onExposureProgress)
        self.instrument.exposer.exposureFinished.disconnect(self.onExposureFinished)

    def onExposureProgress(self, prefix: str, fsn: int, currenttime: float, starttime: float, endtime: float):
        self.progress.emit(f'Exposing {prefix}/{fsn}, remaining time {endtime-currenttime:.1f} sec', int(1000*(currenttime-starttime)/(endtime-starttime)), 1000)

    def onExposureFinished(self, success: bool):
        self.disconnectExposer()
        if success:
            self.finish(True)
        else:
            self.fail(False)

    def initialize(self, exptime: float, prefix: str):
        self.connectExposer()
        try:
            self.instrument.exposer.startExposure(prefix, exptime)
        except:
            self.disconnectExposer()
            raise


class ExposeMulti(Expose):
    name = 'exposemulti'
    description = 'Expose multiple images'
    arguments = [FloatArgument('exptime', 'Exposure time in seconds'),
                 IntArgument('nimages', 'Number of images'),
                 StringArgument('prefix', 'Exposure prefix', defaultvalue='crd'),
                 FloatArgument('delay', 'Delay between exposures in seconds', defaultvalue=0.003)]

    def initialize(self, exptime: float, nimages:int, prefix: str, delay: float):
        self.connectExposer()
        try:
            self.instrument.exposer.startExposure(prefix, exptime, nimages, delay)
        except:
            self.disconnectExposer()
            raise
