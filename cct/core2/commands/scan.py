import logging

from PyQt5.QtCore import pyqtSlot as Slot

from .commandargument import StringArgument, FloatArgument, IntArgument
from .command import Command

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ScanCommand(Command):
    name = 'scan'
    description = 'Do a scan measurement with absolute positioning'
    arguments = [StringArgument('motor', 'name of the motor'),
                 FloatArgument('start', 'starting position (inclusive)'),
                 FloatArgument('end', 'end position (inclusive)'),
                 IntArgument('Npoints', 'number of points'),
                 FloatArgument('exptime', 'exposure time at each point'),
                 StringArgument('comment', 'description of the scan')]

    def stop(self):
        self.instrument.scan.stopScan()


    def connectScanComponent(self):
        self.instrument.scan.scanstarted.connect(self.onScanStarted)
        self.instrument.scan.scanfinished.connect(self.onScanFinished)
        self.instrument.scan.scanprogress.connect(self.onScanProgress)

    def disconnectScanComponent(self):
        self.instrument.scan.scanstarted.disconnect(self.onScanStarted)
        self.instrument.scan.scanfinished.disconnect(self.onScanFinished)
        self.instrument.scan.scanprogress.disconnect(self.onScanProgress)

    def initialize(self, motor: str, start: float, end: float, Npoints: int, exptime: float, comment:str):
        relative = self.name == 'scanrel'
        self.connectScanComponent()
        try:
            self.message.emit(
                f'Starting {"absolute" if not relative else "relative"} scan with '
                f'motor {motor} from {start} to {end} ({Npoints} steps, step size '
                f'{(end-start)/(Npoints-1)} with {exptime:.3f} seconds exposure time')
            self.instrument.scan.startScan(
                motorname=motor, rangemin=start, rangemax=end, steps=Npoints, countingtime=exptime, comment=comment,
                relative=relative, movemotorback=False, shutter=False)
        except:
            self.disconnectScanComponent()
            raise

    @Slot(int, int)
    def onScanStarted(self, scanindex: int, steps: int):
        self.message.emit(f'Started scan #{scanindex}')

    @Slot(bool, int, str)
    def onScanFinished(self, success: bool, scanindex: int, message: str):
        self.disconnectScanComponent()
        if success:
            self.message.emit(f'Scan {scanindex} finished successfully. Message: {message}')
            self.finish(scanindex)
        else:
            self.fail(message)

    @Slot(float, float, float, str)
    def onScanProgress(self, start: float, end: float, current: float, message: str):
        logger.debug(f'Scan progress: {start=}, {end=}, {current=}, {message=}')
        if start != end:
            self.progress.emit(message, int(1000*(current-start)/(end-start)), 1000)
        else:
            self.progress.emit(message, 0, 0)


class ScanRelCommand(ScanCommand):
    name = 'scanrel'
    description = 'Do a scan measurement, relatively to the current position of the motor'

    arguments = [StringArgument('motor', 'name of the motor'),
                 FloatArgument('halfwidth', 'half width of the scan interval'),
                 IntArgument('Npoints', 'number of points'),
                 FloatArgument('exptime', 'exposure time at each point'),
                 StringArgument('comment', 'description of the scan')]

    def initialize(self, motor:str, halfwidth: float, Npoints: int, exptime: float, comment:str):
        super().initialize(motor, -halfwidth, halfwidth, Npoints, exptime, comment)