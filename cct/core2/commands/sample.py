from .command import Command
from .commandargument import StringArgument


class SetSample(Command):
    name = 'sample'
    description = 'Move the sample stage'
    arguments = [StringArgument('sample', 'Name of the sample')]

    def connectSampleStore(self):
        self.instrument.samplestore.movingToSample.connect(self.onMovingToSample)
        self.instrument.samplestore.movingFinished.connect(self.onMovingFinished)

    def disconnectSampleStore(self):
        self.instrument.samplestore.movingToSample.disconnect(self.onMovingToSample)
        self.instrument.samplestore.movingFinished.disconnect(self.onMovingFinished)

    def initialize(self, sample: str):
        self.connectSampleStore()
        try:
            self.instrument.samplestore.moveToSample(sample)
            self.message.emit(f'Moving to sample {sample}')
        except:
            self.disconnectSampleStore()
            raise

    def onMovingToSample(self, samplename: str, motorname: str, where: float, start: float, end: float):
        self.progress.emit(
            f'Moving to sample {samplename}. Motor {motorname} is at {where:.3f}.',
            int(1000*(where-start)/(end-start)), 1000)

    def onMovingFinished(self, success: bool, samplename: str):
        self.disconnectSampleStore()
        if success:
            self.instrument.samplestore.setCurrentSample(samplename)
            self.finish(samplename)
        else:
            self.message.emit(f'Error while moving to sample {samplename}.')
            self.fail(samplename)

    def stop(self):
        self.instrument.samplestore.stopMotors()
        self.message.emit('Stopping command on user request')
