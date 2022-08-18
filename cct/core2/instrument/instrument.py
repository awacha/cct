import logging
from typing import Dict, Optional, List

import h5py
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from .components.auth import UserManager
from .components.beamstop import BeamStop
from .components.calibrants.calibrants import CalibrantStore
from .components.component import Component
from .components.datareduction.datareduction import DataReduction
from .components.devicemanager import DeviceManager
from .components.devicestatus import DeviceStatus, DeviceLogManager
from .components.expose import Exposer
from .components.geometry.geometry import Geometry
from .components.interpreter import Interpreter
from .components.io import IO
from .components.motors import Motors
from .components.notifier import Notifier
from .components.projects import ProjectManager
from .components.samples import SampleStore
from .components.scan import ScanStore
from .components.sensors import Sensors
from .components.transmission import TransmissionMeasurement
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
    devicelogmanager: DeviceLogManager
    devicestatus: DeviceStatus
    geometry: Geometry
    calibrants: CalibrantStore
    scan: ScanStore
    auth: UserManager
    projects: ProjectManager
    exposer: Exposer
    transmission: TransmissionMeasurement
    sensors: Sensors
    notifier: Notifier
    stopping: bool = False
    running: bool = False
    shutdown = Signal()
    panicAcknowledged = Signal()
    online: bool = False
    components: Dict[str, Component] = None
    _panic_components: Optional[List[List[str]]] = None
    panicreason: Optional[str] = None

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
        except EOFError:
            logger.warning(f'Empty or invalid config file {configfile}.')
            pass
        logger.debug('Initializing components')
        # initializing components
        self.components = {}
        for componentname, componentclass in [
            ('io', IO),
            ('auth', UserManager),
            ('samplestore', SampleStore),
            ('devicemanager', DeviceManager),
            ('devicestatus', DeviceStatus),
            ('motors', Motors),
            ('interpreter', Interpreter),
            ('beamstop', BeamStop),
            ('geometry', Geometry),
            ('calibrants', CalibrantStore),
            ('scan', ScanStore),
            ('projects', ProjectManager),
            ('exposer', Exposer),
            ('datareduction', DataReduction),
            ('transmission', TransmissionMeasurement),
            ('sensors', Sensors),
            ('notifier', Notifier),
            ('devicelogmanager', DeviceLogManager),
        ]:
            ### NOTE! When you add a new component, add a corresponding entry in the panic() method as well!
            comp = componentclass(config=self.config, instrument=self)
            setattr(self, componentname, comp)
            self.components[componentname] = comp
            comp.started.connect(self.onComponentStarted)
            comp.stopped.connect(self.onComponentStopped)

    @Slot()
    def onComponentStarted(self):
        if all([c.running() for n, c in self.components.items()]):
            logger.info('All components are up and running.')

    @Slot()
    def onComponentStopped(self):
        logger.debug(
            f'Currently running components: {", ".join(c for c in self.components if self.components[c].running())}')
        if all([not c.running() for n, c in self.components.items()]):
            self.running = False
            self.stopping = False
            logger.debug('Emitting instrument shutdown signal.')
            self.shutdown.emit()

    @Slot()
    def onComponentPanicAcknowledged(self):
        component: Component = self.sender()
        try:
            componentname = [cn for cn in self.components if self.components[cn] is component][0]
        except IndexError:
            pass  # happens at the first round.
        else:
            component.panicAcknowledged.disconnect(self.onComponentPanicAcknowledged)
            logger.info(f'Component {componentname} acknowledged the panic situation.')
            try:
                self._panic_components[0].remove(componentname)
            except ValueError:
                # should not happen, but who knows
                pass
        if self._panic_components[0]:
            # still waiting for some components from this round
            return
        # all components of this round have acted, notify the new ones
        del self._panic_components[0]
        if not self._panic_components:
            # all components done
            logger.info('Panic sequence finished.')
            self.panicAcknowledged.emit()
            # stop the instrument.
            self.stop()
            return
        for cname in self._panic_components[0]:
            self.components[cname].panicAcknowledged.connect(self.onComponentPanicAcknowledged)
            logger.info(f'Notifying component {cname} on the panic situation.')
            self.components[cname].panichandler()

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

    def panic(self, reason: str = 'Unspecified reason'):
        """Start the panic sequence

        Whenever something really bad happens, the panic sequence ensures that everything is put in a clean state and
        powered off.

        Some events which might evoke the panic sequence:
        - the user pressing the PANIC button
        - serious trouble with the X-ray source
        - grid power outage reported by the UPS
        """
        if self._panic_components is not None:
            logger.error(f'Another panic occurred while handling a panic situation. Reason: {reason}')
            return
        self.panicreason = reason
        self._panic_components = [
            [],
            ['notifier'],
            ['interpreter'],
            ['scan', 'transmission'],
            ['exposer'],
            ['beamstop', 'samplestore'],
            ['motors', 'sensors'],
            ['devicestatus', 'devicelogmanager'],
            ['devicemanager'],
            ['projects'],
            ['calibrants', 'auth', 'io', 'geometry', 'datareduction'],
        ]
        self.onComponentPanicAcknowledged()

    def toNeXus(self, entrygrp: h5py.Group) -> h5py.Group:
        """Write NeXus-formatted data to a HDF5 group about the instrument

        Parameter `entrygrp` is the NXentry group into which the NXinstrument and its subgroups will be placed

        :param entrygrp: group of the NXentry
        :type entrygrp: h5py.Group instance
        """
        instgroup = entrygrp.create_group('instrument')
        instgroup.attrs['NX_class'] = 'NXinstrument'
        instgroup.create_dataset('name', data='Creative Research Equipment for DiffractiOn').attrs.update({
            'short_name': 'CREDO'})
        sample = self.samplestore.currentSample()
        self.beamstop.toNeXus(instgroup)
        self.devicemanager.toNeXus(instgroup)
        self.motors.toNeXus(instgroup)
        self.geometry.toNeXus(instgroup, 0.0 if sample is None else sample.distminus[0])
        return entrygrp
