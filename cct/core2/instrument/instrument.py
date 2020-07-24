import logging

from PyQt5 import QtCore

from .components.beamstop import BeamStop
from .components.devicemanager import DeviceManager
from .components.interpreter import Interpreter
from .components.io import IO
from .components.motors import Motors
from .components.samples import SampleStore
from ..config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Instrument(QtCore.QObject):
    config: Config
    io: IO
    beamstop: BeamStop
    interpreter: Interpreter
    samplestore: SampleStore
    motors: Motors
    devicemanager: DeviceManager
    stopping: bool=False
    running: bool=False
    shutdown = QtCore.pyqtSignal()

    def __init__(self, configfile: str):
        super().__init__()
        self.config = Config(autosave=True)
        self.createDefaultConfig()
        logger.debug(f'Using config file {configfile}')
        self.config.load(configfile)
        self.io = IO(config=self.config, instrument=self)
        self.samplestore = SampleStore(config=self.config, instrument=self)
        self.devicemanager = DeviceManager(config=self.config, instrument=self)
        self.motors = Motors(config=self.config, instrument=self)
        self.interpreter = Interpreter(config=self.config, instrument=self)
        self.beamstop = BeamStop(config=self.config, instrument=self)
        self.devicemanager.stopped.connect(self.onDeviceManagerStopped)

    #        self.start()

    def start(self):
        logger.info('Starting Instrument')
        self.running = True
        self.devicemanager.connectDevices()

    def stop(self):
        logger.info('Stopping Instrument')
        self.stopping = True
        self.devicemanager.disconnectDevices()

    def onDeviceManagerStopped(self):
        self.running = False
        self.stopping = False
        logger.debug('Emitting instrument shutdown signal.')
        self.shutdown.emit()

    def createDefaultConfig(self):
        self.config['path'] = {
            'directories': {
                'log': 'log',
                'images': 'images',
                'param': 'param',
                'config': 'config',
                'mask': 'mask',
                'nexus': 'nexus',
                'eval1d': 'eval1d',
                'eval2d': 'eval2d',
                'param_override': 'param_override',
                'scan': 'scan',
                'images_detector': ['/disk2/images', '/home/det/p2_det/images'],
                'status': 'status',
                'scripts': 'scripts',
            },
            'fsndigits': 5,
            'prefixes': {
                'crd': 'crd',
                'scn': 'scn',
                'tra': 'tra',
                'tst': 'tst',
            },
            'varlogfile': 'varlog.log',
        }
        self.config['beamstop'] = {'in': (0.0, 0.0), 'out': (0.0, 0.0), 'motorx': 'BeamStop_X', 'motory': 'BeamStop_Y'}
        self.config['services'] = {
            'samplestore': {'list': {}, 'active': None, 'motorx': 'Sample_X', 'motory': 'Sample_Y'}

        }
        self.config['motors'] = {}
