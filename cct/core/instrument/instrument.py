import logging
import os
import pickle
import time
import traceback
from typing import List

from gi.repository import GLib

from ..devices.device import DeviceError, Device, DeviceBackend_ModbusTCP, DeviceBackend_TCP
from ..devices.motor import Motor
from ..services import Interpreter, FileSequence, ExposureAnalyzer, SampleStore, Accounting, WebStateFileWriter, \
    Service, TelemetryManager
from ..utils.callback import Callbacks, SignalFlags
from ..utils.telemetry import TelemetryInfo

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DummyTm(object):
    ru_utime = None
    ru_stime = None
    ru_maxrss = None
    ru_minflt = None
    ru_majflt = None
    ru_inblock = None
    ru_oublock = None
    ru_nvcsw = None
    ru_nivcsw = None


class InstrumentError(Exception):
    pass


class Instrument(Callbacks):
    configdir = 'config'
    telemetry_timeout = 0.9
    statusfile_timeout = 30
    memlog_timeout = 60  # write memory usage log
    memlog_file = 'memory.log'

    __signals__ = {
        # emitted when all devices have been initialized.
        'devices-ready': (SignalFlags.RUN_FIRST, None, ()),
        # emitted when telemetry data is obtained from a component. The first
        # argument is the name of the component, the second is the type of the
        # component (service or device), and the third one is the telemetry
        # dictionary.
        'telemetry': (SignalFlags.RUN_FIRST, None, (object, str, object)),
        # emitted when the instrument is finalized: all devices disconnected,
        # all services stopped.
        'shutdown': (SignalFlags.RUN_FIRST, None, ()),
        # emitted when a device is connected successfully. The argument is the device.
        'device-connected': (SignalFlags.RUN_FIRST, None, (object,)),
        # emitted when a device is disconnected. The first argument is the device,
        # the second one is a bool: if the disconnection was expected or not.
        'device-disconnected': (SignalFlags.RUN_FIRST, None, (object, bool)),
    }

    def __init__(self, online):
        Callbacks.__init__(self)
        self._online = online
        self.shutdown_requested = False
        self.devices = {}
        self.pseudo_devices = {}
        self.services = {}
        self.motors = {}
        self.configfile = os.path.join(self.configdir, 'cct.pickle')
        self._initialize_config()
        self._signalconnections = {}
        self._waiting_for_ready = []
        self._telemetries = {}
        self._telemetry_timeout = None
        self._service_connections = {}
        self.starttime = None
        self.load_state()
        self.create_services()

    @property
    def online(self) -> bool:
        return self._online

    def is_busy(self):
        return any([s.is_busy() for s in self.services.values()])

    def start(self):
        """Start operation"""
        self.starttime = time.monotonic()
        self._telemetry_timeout = GLib.timeout_add(self.telemetry_timeout * 1000,
                                                   self.on_telemetry_timeout)
        for s in self.services:
            self.services[s].start()
        logger.info('Started all services.')

    # noinspection PyDictCreation
    def _initialize_config(self):
        """Create a sane configuration in `self.config` from scratch."""
        self.config = {
            'path': {
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
                    'tst': 'tst'
                },
            },
            'geometry': {
                'dist_sample_det': 1000.,
                'dist_sample_det.err': 0.,
                'dist_source_ph1': 100.,
                'dist_ph1_ph2': 100.,
                'dist_ph2_ph3': 1.,
                'dist_ph3_sample': 2.,
                'dist_det_beamstop': 1.,
                'pinhole_1': 1000.,
                'pinhole_2': 300.,
                'pinhole_3': 750.,
                'description': 'Generic geometry, please correct values',
                'beamstop': 4.,
                'wavelength': 0.15418,
                'wavelength.err': 0.15418 * 0.03,
                'beamposx': 330.,
                'beamposy': 257.,
                'pixelsize': 0.172,
                'mask': 'mask.mat'
            },
            'connections': {
                'xray_source': {
                    'host': 'genix.credo',
                    'port': 502,
                    'timeout': 1,
                    'name': 'genix',
                    'classname': 'GeniX'
                },
                'detector': {
                    'host': 'pilatus300k.credo',
                    'port': 41234,
                    'timeout': 0.01,
                    'poll_timeout': 0.01,
                    'name': 'pilatus',
                    'classname': 'Pilatus'
                },
                'vacuum': {
                    'host': 'devices.credo',
                    'port': 2006,
                    'timeout': 0.1,
                    'poll_timeout': 0.1,
                    'name': 'tpg201',
                    'classname': 'TPG201'
                },
                'temperature': {
                    'host': 'devices.credo',
                    'port': 2001,
                    'timeout': 0.1,
                    'poll_timeout': 0.05,
                    'name': 'haakephoenix',
                    'classname': 'HaakePhoenix'
                },
                'tmcm351a': {
                    'host': 'devices.credo',
                    'port': 2003,
                    'timeout': 0.01,
                    'poll_timeout': 0.01,
                    'name': 'tmcm351a',
                    'classname': 'TMCM351'
                },
                'tmcm351b': {
                    'host': 'devices.credo',
                    'port': 2004,
                    'timeout': 0.01,
                    'poll_timeout': 0.01,
                    'name': 'tmcm351b',
                    'classname': 'TMCM351'
                },
                'tmcm6110': {
                    'host': 'devices.credo',
                    'port': 2005,
                    'timeout': 0.01,
                    'poll_timeout': 0.01,
                    'name': 'tmcm6110',
                    'classname': 'TMCM6110'
                },
            },
            'motors': {
                '0': {'name': 'Unknown1', 'controller': 'tmcm351a', 'index': 0},
                '1': {'name': 'Sample_X', 'controller': 'tmcm351a', 'index': 1},
                '2': {'name': 'Sample_Y', 'controller': 'tmcm351a', 'index': 2},
                '3': {'name': 'PH1_X', 'controller': 'tmcm6110', 'index': 0},
                '4': {'name': 'PH1_Y', 'controller': 'tmcm6110', 'index': 1},
                '5': {'name': 'PH2_X', 'controller': 'tmcm6110', 'index': 2},
                '6': {'name': 'PH2_Y', 'controller': 'tmcm6110', 'index': 3},
                '7': {'name': 'PH3_X', 'controller': 'tmcm6110', 'index': 4},
                '8': {'name': 'PH3_Y', 'controller': 'tmcm6110', 'index': 5},
                '9': {'name': 'BeamStop_X', 'controller': 'tmcm351b', 'index': 0},
                '10': {'name': 'BeamStop_Y', 'controller': 'tmcm351b', 'index': 1},
                '11': {'name': 'Unknown2', 'controller': 'tmcm351b', 'index': 2}
            },
            'devices': {
                'genix': {'last_warmup': 0, 'warmup_interval': 24 * 3600, 'last_powered': 0}
            },
            'services': {
                'interpreter': {},
                'samplestore': {'list': [], 'active': None},
                'filesequence': {},
                'exposureanalyzer': {},
                'webstate': {},
                'telemetrymanager': {'memlog_file_basename': 'memlog', 'memlog_interval': 60},
                'accounting': {
                    'operator': 'CREDOoperator',
                    'projectid': 'Project ID',
                    'projectname': 'Project name',
                    'proposer': 'Main proposer',
                    'default_realm': 'MTATTKMFIBNO',
                },
            },
            'scan': {
                'mask': 'mask.mat',
                'mask_total': 'mask.mat',
                'columns': ['FSN', 'total_sum', 'sum', 'total_max', 'max', 'total_beamx', 'beamx',
                            'total_beamy', 'beamy', 'total_sigmax', 'sigmax', 'total_sigmay', 'sigmay',
                            'total_sigma', 'sigma'],
                'scanfile': 'credoscan2.spec'
            },
            'transmission': {
                'nimages': 10,
                'exptime': 0.5,
                'mask': 'mask.mat'},
            'beamstop': {'in': (3, 3), 'out': (3, 10)},
            'calibrants': {
                'Silver behenate': {
                    'Peak #1': {'val': 1.0759, 'err': 0.0007},
                    'Peak #2': {'val': 2.1518, 'err': 0.0014},
                    'Peak #3': {'val': 3.2277, 'err': 0.0021},
                    'Peak #4': {'val': 4.3036, 'err': 0.0028},
                    'Peak #5': {'val': 5.3795, 'err': 0.0035},
                    'Peak #6': {'val': 6.4554, 'err': 0.0042},
                    'Peak #7': {'val': 7.5313, 'err': 0.0049},
                    'Peak #8': {'val': 8.6072, 'err': 0.0056},
                    'Peak #9': {'val': 9.6831, 'err': 0.0063},
                },
                'SBA15': {
                    '(10)': {'val': 0.6839, 'err': 0.0002},
                    '(11)': {'val': 1.1846, 'err': 0.0003},
                    '(20)': {'val': 1.3672, 'err': 0.0002},
                },
                'LaB6': {
                    '(100)': {'val': 15.11501, 'err': 0.00004},
                    '(110)': {'val': 21.37584, 'err': 0.00004},
                    '(111)': {'val': 26.18000, 'err': 0.00004}
                },
            },
            'datareduction': {
                'backgroundname': 'Empty_Beam',
                'darkbackgroundname': 'Dark',
                'absintrefname': 'Glassy_Carbon',
                'absintrefdata': 'config/GC_data_nm.dat',
                'distancetolerance': 100,  # mm
                'mu_air': 1000,  # ToDo
                'mu_air.err': 0,  # ToDo
            },
            'gui': {
                'optimizegeometry': {
                    'spacers': [65, 65, 100, 100, 100, 100, 100, 200, 200, 500, 800],
                    'pinholes': [150, 200, 300, 400, 500, 600, 750, 1000, 1250],
                }
            }
        }

    def save_state(self):
        """Save the current configuration (including that of all devices) to a
        pickle file."""
        for devname, dev in self.devices.items():
            assert isinstance(dev, Device)
            self.config['devices'][devname] = dev.save_state()
        for servname, serv in self.services.items():
            assert isinstance(serv, Service)
            self.config['services'][servname] = serv.save_state()
        with open(self.configfile, 'wb') as f:
            pickle.dump(self.config, f)
        logger.info('Saved state to ' + self.configfile)
        for dev in self.devices.values():
            assert isinstance(dev, Device)
            dev.send_config(self.config)
        for serv in self.services.values():
            assert isinstance(serv, Service)
            serv.update_config(self.config)

    def update_config(self, config_orig, config_loaded):
        """Uppdate the config dictionary in `config_orig` with the loaded
        dictionary in `config_loaded`, recursively."""
        for c in config_loaded:
            if c not in config_orig:
                config_orig[c] = config_loaded[c]
            elif isinstance(config_orig[c], dict) and isinstance(config_loaded[c], dict):
                self.update_config(config_orig[c], config_loaded[c])
            else:
                config_orig[c] = config_loaded[c]
        return

    def load_state(self):
        """Load the saved configuration file. This is only useful before
        connecting to devices, because status of the back-end process is
        not updated by Device._load_state()."""
        with open(self.configfile, 'rb') as f:
            config_loaded = pickle.load(f)
        config_loaded = self.fix_config(config_loaded)
        self.update_config(self.config, config_loaded)

    # noinspection PyMethodMayBeStatic
    def fix_config(self, config):
        """Fix some previous discrepancies in the config dict."""
        logger.debug('Fixing "connections" section in the config.')
        for subsection in ['environmentcontrollers', 'motorcontrollers']:
            try:
                for c in list(config['connections'][subsection]):
                    config['connections'][c] = config['connections'][subsection][c]
                del config['connections'][subsection]
            except KeyError as ke:
                logger.debug('KeyError: {}'.format(ke.args[0]))
                pass
        return config

    def _connect_signals(self, device: Device):
        """Connect signal handlers of a device.

        device: the device object, an instance of
            cct.core.devices.device.Device
        """
        self._signalconnections[device.name] = [device.connect('ready', self.on_ready),
                                                device.connect('disconnect', self.on_disconnect),
                                                device.connect('telemetry', self.on_telemetry)]

    def disconnect_signals(self, device: Device):
        """Disconnect signal handlers from a device."""
        try:
            for c in self._signalconnections[device.name]:
                device.disconnect(c)
            del self._signalconnections[device.name]
        except (AttributeError, KeyError):
            pass

    def get_beamstop_state(self, **kwargs):
        """Check if beamstop is in the beam or not.

        Returns a string:
            'in' if the beamstop motors are at their calibrated in-beam position
            'out' if the beamstop motors are at their calibrated out-of-beam position
            'unknown' otherwise

        You can override motor positions in keyword arguments, as in
            get_beamstop_state(BeamStop_X=10, BeamStop_Y=3)
        """
        bsx = kwargs.pop('BeamStop_X', None)
        bsy = kwargs.pop('BeamStop_Y', None)
        try:
            if bsx is None:
                bsx = self.motors['BeamStop_X'].where()
            if bsy is None:
                bsy = self.motors['BeamStop_Y'].where()
        except KeyError:
            raise
        if abs(bsx - self.config['beamstop']['in'][0]) < 0.001 and abs(bsy - self.config['beamstop']['in'][1]) < 0.001:
            return 'in'
        if abs(bsx - self.config['beamstop']['out'][0]) < 0.001 and abs(
                        bsy - self.config['beamstop']['out'][1]) < 0.001:
            return 'out'
        return 'unknown'

    def connect_devices(self):
        """Try to connect to all devices. Send error logs on failures. Return
        a list of the names of unsuccessfully connected devices."""
        if not self._online:
            logger.warning('Not connecting to hardware: we are not on-line.')
            return

        def get_subclasses(cl) -> List:
            """Recursively get a flat list of subclasses of `cls`"""
            scl = [cl]
            for c in cl.__subclasses__():
                scl.extend(get_subclasses(c))
            return scl

        # get all the device classes, i.e. descendants of Device.
        # noinspection PyTypeChecker
        device_classes = get_subclasses(Device)

        # initialize all the devices: instantiate classes, connect signal handlers,
        # establish connections to the hardware and load state information. The class
        # instances are added to the dict `self.devices`, the keys being those given in
        # cfg['name'].
        unsuccessful = []
        for entryname in sorted(self.config['connections']):
            logger.debug('Connecting device {}'.format(entryname))
            cfg = self.config['connections'][entryname]  # shortcut
            # avoid establishing another connection to the device.
            if cfg['name'] in self.devices:
                logger.warn('Not connecting {} again.'.format(cfg['name']))
                continue
            # get the appropriate class
            cls = [d for d in device_classes if d.__name__ == cfg['classname']]
            assert (len(cls) == 1)  # a single class must exist.
            cls = cls[0]

            dev = cls(cfg['name'])  # instantiate the class
            assert (isinstance(dev, Device))
            self.devices[cfg['name']] = dev
            try:
                # connect signal handlers
                self._connect_signals(dev)
                # connect to the hardware
                assert issubclass(cls, Device)
                if issubclass(cls.backend_class, DeviceBackend_ModbusTCP):
                    dev.connect_device(cfg['host'], cfg['port'], cfg['timeout'])
                elif issubclass(cls.backend_class, DeviceBackend_TCP):
                    dev.connect_device(cfg['host'], cfg['port'], cfg['timeout'], cfg['poll_timeout'])
                else:
                    raise TypeError(cls.backend_class)
                # load the state
                try:
                    dev.load_state(self.config['devices'][cfg['name']])
                except KeyError:
                    # skip if there is no saved state to the device
                    pass
                self._waiting_for_ready.append(dev.name)
            except DeviceError:
                # on failure of connecting to the hardware, disconnect signal handlers, delete the instance and
                # note the name of this entry for returning to the caller.
                self.disconnect_signals(dev)
                logger.error(
                    'Cannot connect to device {}: {}'.format(cfg['name'], traceback.format_exc()))
                del self.devices[cfg['name']]
                del dev
                unsuccessful.append(cfg['name'])
        logger.debug('All devices are connected to. Creating shortcuts.')
        # at this point, all devices are initialized. We will create some shortcuts to special devices:
        try:
            self.pseudo_devices['xray_source'] = self.devices[self.config['connections']['xray_source']['name']]
        except KeyError:
            pass
        try:
            self.pseudo_devices['detector'] = self.devices[self.config['connections']['detector']['name']]
        except KeyError:
            pass
        try:
            self.pseudo_devices['vacuum'] = self.devices[self.config['connections']['vacuum']['name']]
        except KeyError:
            pass
        try:
            self.pseudo_devices['temperature'] = self.devices[self.config['connections']['temperature']['name']]
        except KeyError:
            pass
        logger.debug('Instantiating motors.')
        # Instantiate motors
        for m in self.config['motors']:
            cfg = self.config['motors'][m]
            try:
                self.motors[cfg['name']] = Motor(self.devices[cfg['controller']],
                                                 cfg['index'], cfg['name'])
                self.pseudo_devices['Motor_' + cfg['name']] = self.motors[cfg['name']]
            except KeyError:
                logger.error('Cannot find controller for motor ' + cfg['name'])
        logger.debug('Motors instantiated.')
        logger.debug('Not connected devices: {}'.format(str(unsuccessful)))
        return unsuccessful

    def get_device(self, devicename: str):
        try:
            return self.pseudo_devices[devicename]
        except KeyError:
            return self.devices[devicename]

    def on_telemetry(self, device, telemetry):
        self.services['telemetrymanager'].incoming_telemetry(device.name, telemetry)

    def on_ready(self, device):
        try:
            self._waiting_for_ready.remove(device.name)
        except ValueError:
            pass
        self.emit('device-connected', device)
        if not self._waiting_for_ready:
            self.emit('devices-ready')
            self.services['webstate'].write_statusfile()
            logger.debug('All ready.')
        else:
            logger.debug('Waiting for ready: ' + ', '.join(self._waiting_for_ready))

    def on_disconnect(self, device: Device, because_of_failure: bool):
        logger.debug('Device {} disconnected. Because of failure: {}'.format(
            device.name, because_of_failure))
        self.emit('device-disconnected', device, because_of_failure)
        if device.name in self._waiting_for_ready:
            logger.warning('Not reconnecting to device ' + device.name + ': disconnected while waiting for get ready.')
            self._waiting_for_ready.remove(device.name)
            self.on_ready(device)  # check if all other devices are ready
            return False
        if not device.is_ready():
            logger.warning('Not reconnecting to device ' + device.name + ': it has disconnected before ready.')
            return False
        if because_of_failure and not self.shutdown_requested:
            # attempt to reconnect
            self._waiting_for_ready = [w for w in self._waiting_for_ready if w != device.name]
            for i in range(3):
                try:
                    device.reconnect_device()
                    self._waiting_for_ready.append(device.name)
                    return True
                except Exception as exc:
                    logger.warning('Exception while reconnecting to device {}: {}, {}'.format(
                        device.name, exc, traceback.format_exc()))
                    time.sleep(1)  # a blocking sleep. Keep the other parts of this program from accessing the device.
            if device.name not in self._waiting_for_ready:
                logger.error('Cannot reconnect to device ' + device.name + '.')
            return False
        else:
            # this was a normal, requested disconnection.
            self._try_to_send_stopped_signal()

    def create_services(self):
        for sname, sclass, signals in [
            ('interpreter', Interpreter, {}),
            ('filesequence', FileSequence, {}),
            ('samplestore', SampleStore, {}),
            ('exposureanalyzer', ExposureAnalyzer, {'telemetry': self.on_telemetry}),
            ('accounting', Accounting, {}),
            ('webstate', WebStateFileWriter, {}),
            ('telemetrymanager', TelemetryManager, {}),
        ]:
            assert issubclass(sclass, Service)
            logger.debug('Initializing service {}'.format(sname))
            assert sclass.name == sname
            self.services[sname] = sclass(self, self.configdir, self.config['services'][sname])
            self._service_connections[sname] = [self.services[sname].connect('shutdown', self.on_service_shutdown)]
            for sig in signals:
                self._service_connections[sname].append(self.services[sname].connect(sig, signals[sig]))

    def on_service_shutdown(self, service):
        logger.debug('Service {} has shut down.'.format(service.name))
        for c in self._service_connections[service.name]:
            service.disconnect(c)
        self._service_connections[service.name] = []
        self._try_to_send_stopped_signal()

    def on_telemetry_timeout(self):
        """Timer function which periodically requests telemetry from all the
        components."""
        self.services['telemetrymanager'].incoming_telemetry('main', TelemetryInfo())
        return True

    def shutdown(self):
        self.shutdown_requested = True
        for d in self.devices:
            self.devices[d].disconnect_device()
        for s in self.services:
            self.services[s].stop()
        self._try_to_send_stopped_signal()

    def _try_to_send_stopped_signal(self):
        if not self.shutdown_requested:
            return False
        running_devices = [d for d in self.devices if self.devices[d].get_connected()]
        running_services = [s for s in self.services if self.services[s].is_running()]
        if not running_devices and not running_services:
            self.shutdown_requested = False
            self.emit('shutdown')
        else:
            logger.debug('Not shutting instrument down yet. Outstanding devices: {}. Outstanding services: {}.'.format(
                ', '.join([self.devices[d].name for d in running_devices]),
                ', '.join([self.services[s].name for s in running_services])
            ))
