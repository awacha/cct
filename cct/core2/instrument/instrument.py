import logging
from typing import Dict

from PyQt5 import QtCore

from .components.component import Component
from .components.beamstop import BeamStop
from .components.calibrants.calibrants import CalibrantStore
from .components.devicemanager import DeviceManager
from .components.geometry.geometry import Geometry
from .components.interpreter import Interpreter
from .components.io import IO
from .components.motors import Motors
from .components.samples import SampleStore
from .components.scan import ScanStore
from .components.auth import UserManager
from .components.projects import ProjectManager
from .components.expose import Exposer
from .components.datareduction.datareduction import DataReduction
from .components.transmission import TransmissionMeasurement
from .components.sensors import Sensors
from ..config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Instrument(QtCore.QObject):
    _singleton_instance: "Instrument" = None
    config: Config
    io: IO
    beamstop: BeamStop
    interpreter: Interpreter
    samplestore: SampleStore
    motors: Motors
    devicemanager: DeviceManager
    geometry: Geometry
    calibrants: CalibrantStore
    scan: ScanStore
    auth: UserManager
    projects: ProjectManager
    exposer: Exposer
    transmission: TransmissionMeasurement
    sensors: Sensors
    stopping: bool = False
    running: bool = False
    shutdown = QtCore.pyqtSignal()
    online: bool = False
    components: Dict[str, Component] = None

    def __init__(self, configfile: str):
        if type(self)._singleton_instance is not None:
            raise RuntimeError('Only one instance can exist from Instrument.')
        type(self)._singleton_instance = self
        super().__init__()
        self.online = False
        self.config = Config()
        self.createDefaultConfig()
        logger.debug(f'Using config file {configfile}')
        try:
            self.config.load(configfile)
        except FileNotFoundError:
            logger.warning(f'Config file {configfile} does not exist.')
            pass

        # initializing components
        self.components = {}
        for componentname, componentclass in [
            ('io', IO),
            ('samplestore', SampleStore),
            ('devicemanager', DeviceManager),
            ('motors', Motors),
            ('interpreter', Interpreter),
            ('beamstop', BeamStop),
            ('geometry', Geometry),
            ('calibrants', CalibrantStore),
            ('scan', ScanStore),
            ('auth', UserManager),
            ('projects', ProjectManager),
            ('exposer', Exposer),
            ('datareduction', DataReduction),
            ('transmission', TransmissionMeasurement),
            ('sensors', Sensors),
        ]:
            comp = componentclass(config=self.config, instrument=self)
            setattr(self, componentname, comp)
            self.components[componentname] = comp
            comp.started.connect(self.onComponentStarted)
            comp.stopped.connect(self.onComponentStopped)

    def onComponentStarted(self):
        if all([c.running() for n, c in self.components.items()]):
            logger.info('All components are up and running.')

    def onComponentStopped(self):
        logger.debug(f'Currently running components: {", ".join(c for c in self.components if self.components[c].running())}')
        if all([not c.running() for n, c in self.components.items()]):
            self.running = False
            self.stopping = False
            logger.debug('Emitting instrument shutdown signal.')
            self.shutdown.emit()

    def setOnline(self, online: bool):
        self.online = online
        logger.info(f'Running {"on-line" if online else "off-line"}')

    def start(self):
        logger.info('Starting Instrument')
        self.running = True
        for component in self.components:
            logger.info(f'Starting component {component}')
            self.components[component].startComponent()

    def stop(self):
        logger.info('Stopping Instrument')
        self.stopping = True
        for component in reversed(self.components):
            logger.info(f'Stopping component {component}')
            self.components[component].stopComponent()
        self.devicemanager.disconnectDevices()

    def createDefaultConfig(self):
        self.config['beamstop'] = {'in': (0.0, 0.0), 'out': (0.0, 0.0), 'motorx': 'BeamStop_X', 'motory': 'BeamStop_Y'}
        self.config['services'] = {
            'samplestore': {'list': {}, 'active': None, 'motorx': 'Sample_X', 'motory': 'Sample_Y'}
        }
        self.config['motors'] = {}
        self.config['geometry'] = {
            'choices': {
                'spacers': [],
                'flightpipes': [],
                'beamstops': [],
                'pinholes': {1: [], 2: [], 3: []}},
            'dist_source_ph1': 0,
            'dist_ph3_sample': 0,
            'dist_det_beamstop': 0,
        }
        self.config['calibrants'] = {}

    @classmethod
    def instance(cls) -> "Instrument":
        return cls._singleton_instance

    def saveConfig(self):
        for component in self.components.values():
            component.saveToConfig()
        self.config.save(self.config.filename)