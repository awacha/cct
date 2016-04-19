import datetime
import logging
import multiprocessing
import os
import pickle
import resource
import time
import traceback

import psutil

from .motor import Motor
from ..devices.circulator import HaakePhoenix
from ..devices.detector import Pilatus
from ..devices.device import DeviceError
from ..devices.motor import TMCM351, TMCM6110
from ..devices.vacuumgauge import TPG201
from ..devices.xray_source import GeniX
from ..services import Interpreter, FileSequence, ExposureAnalyzer, SampleStore, Accounting, WebStateFileWriter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from gi.repository import GObject, GLib


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


def get_telemetry():
    vm=psutil.virtual_memory()
    sm=psutil.swap_memory()
    la=', '.join([str(f) for f in os.getloadavg()])
    return {'processname': multiprocessing.current_process().name,
            'self': resource.getrusage(resource.RUSAGE_SELF),
            'children': resource.getrusage(resource.RUSAGE_CHILDREN),
            'inqueuelen': 0,
            'freephysmem':vm.available,
            'totalphysmem':vm.total,
            'freeswap':sm.free,
            'totalswap':sm.total,
            'loadavg':la,
            }

class Instrument(GObject.GObject):
    configdir = 'config'
    telemetry_timeout = 0.9
    statusfile_timeout = 30

    __gsignals__ = {
        # emitted when all devices have been initialized.
        'devices-ready': (GObject.SignalFlags.RUN_FIRST, None, ()),
        # emitted when telemetry data is obtained from a component. The first
        # argument is the name of the component, the second is the type of the
        # component (service or device), and the third one is the telemetry
        # dictionary.
        'telemetry': (GObject.SignalFlags.RUN_FIRST, None, (object, str, object)),
    }

    def __init__(self, online):
        self._starttime=datetime.datetime.now()
        GObject.GObject.__init__(self)
        self._online = online
        self.devices = {}
        self.services = {}
        self.xray_source = None
        self.detector = None
        self.motorcontrollers = {}
        self.motors = {}
        self.environmentcontrollers = {}
        self.configfile = os.path.join(self.configdir, 'cct.pickle')
        self._initialize_config()
        self._signalconnections = {}
        self._waiting_for_ready = []
        self._telemetries = {}
        self.busy=multiprocessing.Event()
        self.load_state()
        self.create_services()

    def start(self):
        """Start operation"""
        self._telemetry_timeout = GLib.timeout_add(self.telemetry_timeout * 1000,
                                                   self.on_telemetry_timeout)
        for s in self.services:
            s.start()
        logger.info('Started services.')

    def _initialize_config(self):
        """Create a sane configuration in `self.config` from sratch."""
        self.config = {}
        self.config['path'] = {}
        self.config['path']['directories'] = {'log': 'log',
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
                                              }
        self.config['path']['fsndigits'] = 5
        self.config['path']['prefixes'] = {'crd': 'crd',
                                           'scn': 'scn',
                                           'tra': 'tra',
                                           'tst': 'tst'}
        self.config['geometry'] = {'dist_sample_det': 1000.,
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
                                   'mask': 'mask.mat'}
        self.config['connections'] = {}
        self.config['connections']['xray_source'] = {'host': 'genix.credo',
                                                     'port': 502,
                                                     'timeout': 1,
                                                     'name': 'genix'}
        self.config['connections']['detector'] = {'host': 'pilatus300k.credo',
                                                  'port': 41234,
                                                  'timeout': 0.01,
                                                  'poll_timeout': 0.01,
                                                  'name': 'pilatus'}
        self.config['connections']['environmentcontrollers'] = {}
        self.config['connections']['environmentcontrollers']['vacuum'] = {
            'host': 'devices.credo',
            'port': 2006,
            'timeout': 0.1,
            'poll_timeout': 0.1,
            'name': 'tpg201'}
        self.config['connections']['environmentcontrollers']['temperature'] = {
            'host': 'devices.credo',
            'port': 2001,
            'timeout': 0.1,
            'poll_timeout': 0.05,
            'name': 'haakephoenix'}
        self.config['connections']['motorcontrollers'] = {}
        self.config['connections']['motorcontrollers']['tmcm351a'] = {
            'host': 'devices.credo',
            'port': 2003,
            'timeout': 0.01,
            'poll_timeout': 0.01,
            'name': 'tmcm351a'}
        self.config['connections']['motorcontrollers']['tmcm351b'] = {
            'host': 'devices.credo',
            'port': 2004,
            'timeout': 0.01,
            'poll_timeout': 0.01,
            'name': 'tmcm351b'}
        self.config['connections']['motorcontrollers']['tmcm6110'] = {
            'host': 'devices.credo',
            'port': 2005,
            'timeout': 0.01,
            'poll_timeout': 0.01,
            'name': 'tmcm6110'}
        self.config['motors'] = {'0':{'name': 'Unknown1', 'controller': 'tmcm351a', 'index': 0},
                                 '1':{'name': 'Sample_X',
                                     'controller': 'tmcm351a', 'index': 1},
                                 '2':{'name': 'Sample_Y',
                                     'controller': 'tmcm351a', 'index': 2},
                                 '3': {'name': 'PH1_X',
                                     'controller': 'tmcm6110', 'index': 0},
                                 '4': {'name': 'PH1_Y',
                                     'controller': 'tmcm6110', 'index': 1},
                                 '5': {'name': 'PH2_X',
                                     'controller': 'tmcm6110', 'index': 2},
                                 '6': {'name': 'PH2_Y',
                                     'controller': 'tmcm6110', 'index': 3},
                                 '7': {'name': 'PH3_X',
                                     'controller': 'tmcm6110', 'index': 4},
                                 '8': {'name': 'PH3_Y',
                                     'controller': 'tmcm6110', 'index': 5},
                                 '9':{'name': 'BeamStop_X',
                                     'controller': 'tmcm351b', 'index': 0},
                                 '10':{'name': 'BeamStop_Y',
                                     'controller': 'tmcm351b', 'index': 1},
                                 '11':{'name': 'Unknown2', 'controller': 'tmcm351b', 'index': 2}}
        self.config['devices'] = {}
        self.config['services'] = {
            'interpreter': {}, 'samplestore': {'list': [], 'active': None}, 'filesequence': {}, 'exposureanalyzer': {}}
        self.config['services']['accounting'] = {'operator': 'CREDOoperator',
                                                 'projectid': 'Project ID',
                                                 'projectname': 'Project name',
                                                 'proposer': 'Main proposer',
                                                 'default_realm': 'MTATTKMFIBNO',
                                                 }

        self.config['scan'] = {'mask': 'mask.mat',
                               'mask_total': 'mask.mat',
                               'columns': ['FSN', 'total_sum', 'sum', 'total_max', 'max', 'total_beamx', 'beamx', 'total_beamy', 'beamy', 'total_sigmax', 'sigmax', 'total_sigmay', 'sigmay', 'total_sigma', 'sigma'],
                               'scanfile':'credoscan2.spec'}
        self.config['transmission'] = {'empty_sample': 'Empty_Beam', 'nimages': 10, 'exptime': 0.5, 'mask': 'mask.mat'}
        self.config['beamstop'] = {'in': (3, 3), 'out': (3, 10)}
        self.config['calibrants'] = {'Silver behenate': {'Peak #1': {'val': 1.0759, 'err': 0.0007},
                                                         'Peak #2': {'val': 2.1518, 'err': 0.0014},
                                                         'Peak #3': {'val': 3.2277, 'err': 0.0021},
                                                         'Peak #4': {'val': 4.3036, 'err': 0.0028},
                                                         'Peak #5': {'val': 5.3795, 'err': 0.0035},
                                                         'Peak #6': {'val': 6.4554, 'err': 0.0042},
                                                         'Peak #7': {'val': 7.5313, 'err': 0.0049},
                                                         'Peak #8': {'val': 8.6072, 'err': 0.0056},
                                                         'Peak #9': {'val': 9.6831, 'err': 0.0063},
                                                         },
                                     'SBA15': {'(10)': {'val': 0.6839, 'err': 0.0002},
                                               '(11)': {'val': 1.1846, 'err': 0.0003},
                                               '(20)': {'val': 1.3672, 'err': 0.0002},
                                               },
                                     'LaB6': {'(100)': {'val': 15.11501, 'err': 0.00004},
                                              '(110)': {'val': 21.37584, 'err': 0.00004},
                                              '(111)': {'val': 26.18000, 'err': 0.00004}},
                                     }
        self.config['datareduction'] = {'backgroundname': 'Empty_Beam',
                                        'absintrefname': 'Glassy_Carbon',
                                        'absintrefdata': 'config/GC_data_nm.dat',
                                        'distancetolerance': 100,  # mm
                                        'mu_air': 1000,  # ToDo
                                        'mu_air.err': 0  # ToDo
                                        }
        self.config['services']['webstatefilewriter'] = {}

    def save_state(self):
        """Save the current configuration (including that of all devices) to a
        pickle file."""
        for d in self.devices:
            self.config['devices'][d] = self.devices[d]._save_state()
        for service in ['interpreter', 'samplestore', 'filesequence', 'exposureanalyzer', 'accounting']:
            self.config['services'][service] = getattr(
                self, service)._save_state()
        with open(self.configfile, 'wb') as f:
            pickle.dump(self.config, f)
        logger.info('Saved state to %s'%self.configfile)
        self.exposureanalyzer.sendconfig()


    def _update_config(self, config_orig, config_loaded):
        """Uppdate the config dictionary in `config_orig` with the loaded
        dictionary in `config_loaded`, recursively."""
        for c in config_loaded:
            if c not in config_orig:
                config_orig[c] = config_loaded[c]
            elif isinstance(config_orig[c], dict) and isinstance(config_loaded[c], dict):
                self._update_config(config_orig[c], config_loaded[c])
            else:
                config_orig[c] = config_loaded[c]
        return

    def load_state(self):
        """Load the saved configuration file. This is only useful before
        connecting to devices, because status of the back-end process is
        not updated by Device._load_state()."""
        with open(self.configfile, 'rb') as f:
            config_loaded=pickle.load(f)
        self._update_config(self.config, config_loaded)

    def _connect_signals(self, devicename, device):
        """Connect signal handlers of a device.

        devicename: the name of the device (string)
        device: the device object, an instance of
            cct.core.devices.device.Device
        """
        self._signalconnections[devicename] = [device.connect('startupdone', self.on_ready),
                                               device.connect('disconnect', self.on_disconnect),
                                               device.connect('telemetry', self.on_telemetry, devicename)]

    def _disconnect_signals(self, devicename, device):
        try:
            for c in self._signalconnections[devicename]:
                device.disconnect(c)
            del self._signalconnections[device]
        except (AttributeError, KeyError):
            pass

    def get_beamstop_state(self):
        bsy=self.motors['BeamStop_Y'].where()
        bsx=self.motors['BeamStop_X'].where()
        if abs(bsx-self.config['beamstop']['in'][0])<0.001 and abs(bsy-self.config['beamstop']['in'][1])<0.001:
            return 'in'
        if abs(bsx-self.config['beamstop']['out'][0])<0.001 and abs(bsy-self.config['beamstop']['out'][1])<0.001:
            return 'out'
        return 'unknown'

    def connect_devices(self):
        """Try to connect to all devices. Send error logs on failures. Return
        a list of unsuccessfully connected devices."""
        if not self._online:
            logger.info('Not connecting to hardware: we are not on-line.')
        unsuccessful = []
        if self.xray_source is None:
            self.xray_source = GeniX(
                self.config['connections']['xray_source']['name'])
            self.devices[
                self.config['connections']['xray_source']['name']] = self.xray_source
        try:
            self._connect_signals(
                self.config['connections']['xray_source']['name'], self.xray_source)
            self.xray_source.connect_device(self.config['connections']['xray_source']['host'],
                                            self.config['connections'][
                                                'xray_source']['port'],
                                            self.config['connections']['xray_source']['timeout'])
            self._waiting_for_ready.append(self.xray_source._instancename)
        except DeviceError:
            self._disconnect_signals(
                self.config['connections']['xray_source']['name'], self.xray_source)
            logger.error(
                'Cannot connect to X-ray source: ' + traceback.format_exc())
            self.xray_source = None
            del self.devices[self.config['connections']['xray_source']['name']]
            unsuccessful.append(
                self.config['connections']['xray_source']['name'])
        if self.detector is None:
            self.detector = Pilatus(
                self.config['connections']['detector']['name'])
            self.devices[
                self.config['connections']['detector']['name']] = self.detector
        try:
            self._connect_signals(
                self.config['connections']['detector']['name'], self.detector)
            self.detector.connect_device(self.config['connections']['detector']['host'],
                                         self.config['connections'][
                                             'detector']['port'],
                                         self.config['connections'][
                                             'detector']['timeout'],
                                         self.config['connections']['detector']['poll_timeout'])
            self._waiting_for_ready.append(self.detector._instancename)
        except DeviceError:
            self._disconnect_signals(
                self.config['connections']['detector']['name'], self.detector)
            logger.error(
                'Cannot connect to detector: ' + traceback.format_exc())
            self.detector = None
            del self.devices[self.config['connections']['detector']['name']]
            unsuccessful.append(self.config['connections']['detector']['name'])
        for motcont in self.config['connections']['motorcontrollers']:
            cfg = self.config['connections']['motorcontrollers'][motcont]
            if motcont not in self.motorcontrollers:
                if cfg['name'].startswith('tmcm351'):
                    self.motorcontrollers[motcont] = TMCM351(cfg['name'])
                elif cfg['name'].startswith('tmcm6110'):
                    self.motorcontrollers[motcont] = TMCM6110(cfg['name'])
                self.devices[cfg['name']] = self.motorcontrollers[motcont]
            try:
                self._connect_signals(
                    cfg['name'], self.motorcontrollers[motcont])
                self.motorcontrollers[motcont].connect_device(
                    cfg['host'], cfg['port'], cfg['timeout'], cfg['poll_timeout'])
                self._waiting_for_ready.append(cfg['name'])
            except DeviceError:
                self._disconnect_signals(
                    cfg['name'], self.motorcontrollers[motcont])
                logger.error('Cannot connect to motor driver %s: %s' %
                             (cfg['name'], traceback.format_exc()))
                del self.motorcontrollers[cfg['name']]
                del self.devices[cfg['name']]
                unsuccessful.append(cfg['name'])
        for m in self.config['motors']:
            try:
                self.motors[self.config['motors'][m]['name']] = Motor(
                    self.motorcontrollers[self.config['motors'][m]['controller']],
                    self.config['motors'][m]['index'])
            except KeyError:
                logger.error('Cannot find motor %s' % self.config['motors'][m]['name'])
        for envcont in self.config['connections']['environmentcontrollers']:
            cfg = self.config['connections']['environmentcontrollers'][envcont]
            if envcont not in self.environmentcontrollers:
                if envcont == 'temperature':
                    self.environmentcontrollers[envcont] = HaakePhoenix(cfg['name'])
                elif envcont == 'vacuum':
                    self.environmentcontrollers[envcont] = TPG201(cfg['name'])
                self.devices[
                    cfg['name']] = self.environmentcontrollers[envcont]
            try:
                self._connect_signals(
                    cfg['name'], self.environmentcontrollers[envcont])
                self.environmentcontrollers[envcont].connect_device(
                    cfg['host'], cfg['port'], cfg['timeout'], cfg['poll_timeout'])
                self._waiting_for_ready.append(cfg['name'])
            except DeviceError:
                self._disconnect_signals(
                    cfg['name'], self.environmentcontrollers[envcont])
                logger.error('Cannot connect to %s controller: %s' %
                             (envcont, traceback.format_exc()))
                del self.environmentcontrollers[envcont]
                del self.devices[cfg['name']]
                unsuccessful.append(cfg['name'])
        for d in self.devices:
            if d in self.config['devices']:
                self.devices[d]._load_state(self.config['devices'][d])
        return unsuccessful

    def on_telemetry(self, device, telemetry, devicename):
        self._telemetries[devicename] = telemetry
        self.emit('telemetry', devicename, 'device', telemetry)

    def on_ready(self, device):
        try:
            self._waiting_for_ready.remove(device._instancename)
        except ValueError:
            pass
        if not self._waiting_for_ready:
            self.emit('devices-ready')
            self.webstatefilewriter.write_statusfile()
            logger.debug('All ready.')
        else:
            logger.debug('Waiting for ready: '+', '.join(self._waiting_for_ready))

    def on_disconnect(self, device, because_of_failure):
        logger.debug('Device %s disconnected. Because of failure: %s'%(
            device.name, because_of_failure))
        if device.name in self._waiting_for_ready:
            logger.warning('Not reconnecting to device %s: disconnected while waiting for get ready.'%device.name)
            self._waiting_for_ready.remove(device.name)
            self.on_ready(device) # check if all other devices are ready
            return False
        if not device.ready:
            logger.warning('Not reconnecting to device %s: it has disconnected before ready.'%device.name)
            return False
        if because_of_failure:
            # attempt to reconnect
            self._waiting_for_ready = [w for w in self._waiting_for_ready if w != device.name]
            for i in range(3):
                try:
                    device.reconnect_device()
                    self._waiting_for_ready.append(device.name)
                    return True
                except Exception as exc:
                    logger.warning('Exception while reconnecting to device %s: %s, %s' % (
                    device.name, exc, traceback.format_exc()))
                    time.sleep(1)  # a blocking sleep. Keep the other parts of this program from accessing the device.
            if device.name not in self._waiting_for_ready:
                logger.error('Cannot reconnect to device %s.' % device.name)
            return False

    def create_services(self):
        self.interpreter = Interpreter(self)
        self.interpreter._load_state(self.config['services']['interpreter'])
        self.filesequence = FileSequence(self)
        self.filesequence._load_state(self.config['services']['filesequence'])
        self.samplestore = SampleStore(self)
        self.samplestore._load_state(self.config['services']['samplestore'])
        self.exposureanalyzer = ExposureAnalyzer(self)
        self.exposureanalyzer._load_state(
            self.config['services']['exposureanalyzer'])
        self.accounting = Accounting(self)
        self.accounting._load_state(self.config['services']['accounting'])
        self.webstatefilewriter = WebStateFileWriter(self)
        self.webstatefilewriter._load_state(self.config['services']['webstatefilewriter'])

    def on_telemetry_timeout(self):
        """Timer function which periodically requests telemetry from all the
        components."""
        self._telemetries['main'] = get_telemetry()
        for s in ['exposureanalyzer']:
            getattr(self, s).get_telemetry()
        self.emit('telemetry',None, 'service', self.get_telemetry(None))
        return True

    def get_telemetry(self, process=None):
        if process is None:
            tm = {}
            for what in ['self', 'children']:
                tm[what] = DummyTm()
                tm[what].ru_utime = sum([self._telemetries[k][what].ru_utime for k in self._telemetries])
                tm[what].ru_stime = sum([self._telemetries[k][what].ru_stime for k in self._telemetries])
                tm[what].ru_maxrss = sum([self._telemetries[k][what].ru_maxrss for k in self._telemetries])
                tm[what].ru_minflt = sum([self._telemetries[k][what].ru_minflt for k in self._telemetries])
                tm[what].ru_majflt = sum([self._telemetries[k][what].ru_majflt for k in self._telemetries])
                tm[what].ru_inblock = sum([self._telemetries[k][what].ru_inblock for k in self._telemetries])
                tm[what].ru_oublock = sum([self._telemetries[k][what].ru_oublock for k in self._telemetries])
                tm[what].ru_nvcsw = sum([self._telemetries[k][what].ru_nvcsw for k in self._telemetries])
                tm[what].ru_nivcsw = sum([self._telemetries[k][what].ru_nivcsw for k in self._telemetries])
            sm=psutil.swap_memory()
            vm=psutil.virtual_memory()
            la=', '.join([str(f) for f in os.getloadavg()])
            tm['freephysmem']=vm.available
            tm['totalphysmem']=vm.total
            tm['freeswap']=sm.free
            tm['totalswap']=sm.total
            tm['loadavg']=la
        else:
            tm = {'self': self._telemetries[process]['self'],
                  'children': self._telemetries[process]['children'],
                  }
        return tm

    def get_telemetrykeys(self):
        return self._telemetries.keys()
