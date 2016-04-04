import logging
import multiprocessing
import re
import time
from typing import Optional

import dateutil.parser

from .device import Device_TCP, DeviceError, ReadOnlyVariable, CommunicationError, UnknownVariable, InvalidValue, \
    UnknownCommand

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# integer type variables
pilatus_int_variables = ['wpix', 'hpix', 'sel_bank', 'sel_module',
                         'sel_chip', 'diskfree', 'nimages', 'masterPID', 'controllingPID', 'pid']

# float type variables
pilatus_float_variables = ['tau', 'cutoff', 'exptime', 'expperiod', 'temperature0',
                           'temperature1', 'temperature2', 'humidity0', 'humidity1', 'humidity2', 'threshold', 'vcmp',
                           'timeleft']

# datetime type variables
pilatus_date_variables = ['starttime']

# string variables
pilatus_str_variables = ['version', 'gain', 'trimfile', 'cameradef', 'cameraname', 'cameraSN', '_status', 'targetfile',
                         'lastimage', 'lastcompletedimage', 'shutterstate', 'imgpath', 'imgmode', 'filename',
                         'camstate']

# list of regular expressions matching messages from the Pilatus detector. Each
# element of this list is a tuple, the first element being the message class
# code (Socket connection return code in the Pilatus-300k manual), idnum in
# this code. The second element is a regular expression.
#
# Messages from the camserver follow the scheme:
#
# <idnum><space><statuscode><space><message>
#
# where <statuscode> is OK or ERR.
#

RE_FLOAT = r"[+-]?(\d+)*\.?\d+([eE][+-]?\d+)?"
RE_DATE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+"
RE_INT = r"[+-]?\d+"

# ----------- IDNUM == 2 ---------------------------
RE_CAMSETUP = re.compile(
    """Camera definition:
\s+(?P<cameradef>.+)
\s+Camera name: (?P<cameraname>.+), S/N (?P<cameraSN>.+)
\s+Camera state: (?P<camstate>[a-z]+)
\s+Target file: (?P<targetfile>.+)
\s+Time left: (?P<timeleft>{float})
\s+Last image: (?P<lastimage>.+)
\s+Master PID is: (?P<masterPID>{int})
\s+Controlling PID is: (?P<controllingPID>{int})
\s+Exposure time: (?P<exptime>{float})
\s+Last completed image:
\s+(?P<lastcompletedimage>.+)
\s+Shutter is: (?P<shutterstate>.+)""".format(
        int=RE_INT, float=RE_FLOAT, date=RE_DATE).encode(
        'ascii'), re.MULTILINE
)

# ----------- IDNUM == 5 ---------------------------
RE_DISKFREE = re.compile('(?P<diskfree>{int})'.format(int=RE_INT).encode('ascii'))

# ----------- IDNUM == 10 ---------------------------

RE_IMGPATH = re.compile('(?P<imgpath>.+)'.encode('ascii'))

# ----------- IDNUM == 13 ---------------------------

RE_KILL = re.compile(b'kill')

# ----------- IDNUM == 15 ---------------------------

RE_EXPTIME = re.compile(
    "Exposure time set to: (?P<exptime>{float}) sec\.".format(
        float=RE_FLOAT).encode('ascii'))

RE_EXPPERIOD = re.compile(
    "Exposure period set to: (?P<expperiod>{float}) sec".format(
        float=RE_FLOAT).encode('ascii'))

RE_TAU_ON = re.compile(
    "Rate correction is on; tau = (?P<tau>{float}) s, cutoff = (?P<cutoff>{int}) counts".format(
        float=RE_FLOAT, int=RE_INT).encode('ascii'))

RE_TAU_SETON = re.compile(
    "Set up rate correction: tau = (?P<tau>{float}) s".format(float=RE_FLOAT).encode('ascii'))

RE_TAU_SETOFF = re.compile(
    "Turn off rate correction".encode('ascii'))

RE_TAU_OFF = re.compile("Rate correction is off, cutoff = (?P<cutoff>{int}) counts".format(int=RE_INT).encode('ascii'))

RE_NIMAGES = re.compile("N images set to: (?P<nimages>{int})".format(int=RE_INT).encode('ascii'))

RE_EXPSTART = re.compile(
    "Starting (?P<exptime>{float}) second background: (?P<starttime>{date})".format(float=RE_FLOAT, date=RE_DATE).encode(
        'ascii'))

RE_SETTHRESHOLD = re.compile(
    """Settings: (?P<gain>[a-z]+) gain; threshold: (?P<threshold>{float}) eV; vcmp: (?P<vcmp>{float}) V
 Trim file:
  (?P<trimfile>.*)""".format(float=RE_FLOAT).encode('ascii'), re.MULTILINE)

RE_SETTHRESHOLD_ACK = re.compile(b'/tmp/setthreshold.cmd')

RE_IMGMODE = re.compile(
    """ImgMode is (?P<imgmode>.+)""".encode('ascii')
)

# ----------- IDNUM == 16 ---------------------------

RE_PID = re.compile(
    "PID = (?P<pid>{int})".format(int=RE_INT).encode('ascii'))

# ----------- IDNUM == 18 ---------------------------

RE_TELEMETRY = re.compile(
    """=== Telemetry at (?P<telemetry_date>{date}) ===
Image format: (?P<wpix>{int})\(w\) x (?P<hpix>{int})\(h\) pixels
Selected bank: (?P<sel_bank>{int})
Selected module: (?P<sel_module>{int})
Selected chip: (?P<sel_chip>{int})
Channel {int}: Temperature = (?P<temperature0>{float})C, Rel. Humidity = (?P<humidity0>{float})%
Channel {int}: Temperature = (?P<temperature1>{float})C, Rel. Humidity = (?P<humidity1>{float})%
Channel {int}: Temperature = (?P<temperature2>{float})C, Rel. Humidity = (?P<humidity2>{float})%""".format(
        date=RE_DATE, int=RE_INT, float=RE_FLOAT).encode('ascii'), re.MULTILINE)

# ----------- IDNUM == 24 ---------------------------

RE_VERSION = re.compile("Code release:  (?P<version>.*)".encode('ascii'))

# ----------- IDNUM == 215 ---------------------------

RE_THREAD = re.compile(
    """Channel {int}: Temperature = (?P<temperature0>{float})C, Rel. Humidity = (?P<humidity0>{float})%;
Channel {int}: Temperature = (?P<temperature1>{float})C, Rel. Humidity = (?P<humidity1>{float})%;
Channel {int}: Temperature = (?P<temperature2>{float})C, Rel. Humidity = (?P<humidity2>{float})%""".format(
        int=RE_INT, float=RE_FLOAT).encode('ascii'), re.MULTILINE)


class Pilatus(Device_TCP):
    log_formatstr = '{_status}\t{exptime}\t{humidity0}\t{humidity1}\t{humidity2}\t{temperature0}\t{temperature1}\t{temperature2}'

    watchdog_timeout = 20

    backend_interval = 1

    reply_timeout = 20

    _minimum_query_variables = ['gain', 'trimfile', 'nimages', 'cameradef',
                                'imgpath', 'imgmode', 'pid', 'expperiod',
                                'diskfree', 'tau', 'version']

    _all_variables = ['gain', 'threshold', 'vcmp', 'trimfile', 'wpix', 'hpix',
                      'sel_bank', 'sel_module', 'sel_chip', 'humidity0',
                      'humidity1', 'humidity2', 'temperature0', 'temperature1',
                      'temperature2', 'nimages', 'cameradef', 'cameraname',
                      'cameraSN', 'camstate', 'targetfile', 'timeleft',
                      'lastimage', 'masterPID', 'controllingPID', 'exptime',
                      'lastcompletedimage', 'shutterstate', 'imgpath',
                      'imgmode', 'pid', 'expperiod', 'tau', 'cutoff',
                      'diskfree', 'version', 'telemetry_date']

    def __init__(self, *args, **kwargs):
        Device_TCP.__init__(self, *args, **kwargs)
        self._expected_status = 'idle'
        # a flag which has to be acquired when the detector is busy: trimming or exposing.
        self._busysemaphore = multiprocessing.BoundedSemaphore(1)

    def is_busy(self) -> bool:
        return self._busysemaphore.get_value() == 0

    def _query_variable(self, variablename: str, minimum_query_variables: Optional[list] = None) -> bool:
        if variablename is None:
            if self.is_busy():
                # do not initiate query-all-variables if we are exposing or 
                # trimming: the pilatus detector is known to become unresponsive
                # during these times.
                return False
        if not super()._query_variable(variablename):
            # the above call takes care of the variablename==None case as well.
            return False
        if variablename in ['gain', 'threshold', 'vcmp']:
            self._send(b'SetThreshold\n', expected_replies=None)
        elif variablename in ['trimfile', 'wpix', 'hpix', 'sel_bank', 'sel_module', 'sel_chip']:
            self._send(b'Telemetry\n', expected_replies=None)
        elif variablename.startswith('humidity') or variablename.startswith('temperature'):
            self._send(b'THread\n', expected_replies=None)
        elif variablename == 'nimages':
            self._send(b'NImages\n', expected_replies=None)
        elif variablename in ['cameradef', 'cameraname', 'cameraSN', 'camstate', 'targetfile',
                              'timeleft', 'lastimage', 'masterPID', 'controllingPID',
                              'exptime', 'lastcompletedimage', 'shutterstate']:
            self._send(b'camsetup\n', expected_replies=None)
        elif variablename == 'imgpath':
            self._send(b'imgpath\n', expected_replies=None)
        elif variablename == 'imgmode':
            self._send(b'imgmode\n', expected_replies=None)
        elif variablename == 'pid':
            self._send(b'ShowPID\n', expected_replies=None)
        elif variablename == 'expperiod':
            self._send(b'expperiod\n', expected_replies=None)
        elif variablename in ['tau', 'cutoff']:
            self._send(b'tau\n', expected_replies=None)
        elif variablename == 'diskfree':
            self._send(b'df\n', expected_replies=None)
        elif variablename == 'version':
            self._send(b'version\n', expected_replies=None)
        else:
            raise UnknownVariable(variablename)

    def _get_complete_messages(self, message: bytes) -> list:
        return message.split(b'\x18')

    def _handle_end_exposure(self, status: bool, message: bytes) -> None:
        try:
            self._busysemaphore.release()
        except ValueError:
            return
        self._update_variable('_status', 'idle')
        self._update_variable('lastimage', message.decode('utf-8'))
        self._update_variable('starttime', None)
        if status:
            self._update_variable('lastcompletedimage', message.decode('utf-8'))
        self._release_watchdog()

    def _handle_end_trimming(self) -> None:
        # a new threshold has been set, update the variables
        try:
            self._busysemaphore.release()
        except ValueError:
            return
        self._update_variable('_status', 'idle')
        self._query_variable('threshold')
        self._query_variable('tau')
        self._release_watchdog()

    def _handle_start_exposure(self) -> None:
        self._update_variable('_status', self._expected_status)

    def _process_incoming_message(self, message: bytes, original_sent: Optional[bytes] = None):
        self._pat_watchdog()
        self._cleartosend_semaphore.release()
        origmessage = message
        if message.count(b' ') < 2:
            # empty message, like '15 OK', or one without anything, e.g.
            # b'/tmp/setthreshold.cmd'
            idnum, status = message.split(b' ')  # this can raise ValueError, see below.
            message = b''
        else:
            idnum, status, message = message.split(b' ', 2)
        idnum = int(idnum)
        message = message.strip()
        # handle special cases
        if idnum == 1:
            # access denied
            if (message == b'access denied') and (status == b'ERR'):
                raise CommunicationError(
                    'We could only connect to Pilatus in read-only mode')
            else:
                raise DeviceError('Unknown message received from Pilatus: %s' % origmessage)
        elif idnum == 2:
            m = RE_CAMSETUP.match(message)
            if m is None:
                raise DeviceError('Invalid camsetup message from Pilatus: %s' % origmessage)
            gd = m.groupdict()
            for k in ['controllingPID', 'masterPID']:
                gd[k] = int(gd[k])
            for k in ['exptime', 'timeleft']:
                gd[k] = float(gd[k])
            for k in gd:
                self._update_variable(k, gd[k])
        elif idnum == 5:
            m = RE_DISKFREE.match(message)
            if m is None:
                raise DeviceError('Invalid diskfree message from Pilatus: %s' % origmessage)
            self._update_variable('diskfree', int(m.group('diskfree')))
        elif idnum == 7:
            # end of exposure
            self._handle_end_exposure(status == b'OK', message)
        elif idnum == 10:
            m = RE_IMGPATH.match(message)
            if m is None:
                raise DeviceError('Invalid imgpath message from Pilatus: %s' % origmessage)
            self._update_variable('imgpath', m.group('imgpath'))
        elif idnum == 13:
            # killed
            m = RE_KILL.match(message)
            if m is None:
                raise DeviceError('Unknown kill message from Pilatus: %s' % origmessage)
            self._handle_end_exposure(status == b'OK', b'')
        elif idnum == 15:
            m = RE_EXPTIME.match(message)
            if m is not None:
                self._update_variable('exptime', float(m.group('exptime')))
                return
            m = RE_EXPPERIOD.match(message)
            if m is not None:
                self._update_variable('expperiod', float(m.group('expperiod')))
                return
            m = RE_TAU_ON.match(message)
            if m is not None:
                self._update_variable('tau', float(m.group('tau')))
                self._update_variable('cutoff', int(m.group('cutoff')))
                return
            m = RE_TAU_SETON.match(message)
            if m is not None:
                self._update_variable('tau', float(m.group('tau')))
                return
            m = RE_TAU_SETOFF.match(message)
            if m is not None:
                return
            m = RE_TAU_OFF.match(message)
            if m is not None:
                self._update_variable('cutoff', int(m.group('cutoff')))
                return
            m = RE_NIMAGES.match(message)
            if m is not None:
                self._update_variable('nimages', int(m.group('nimages')))
                return
            m = RE_EXPSTART.match(message)
            if m is not None:
                self._update_variable('exptime', float(m.group('exptime')))
                self._update_variable('starttime', dateutil.parser.parse(m.group('starttime')))
                self._handle_start_exposure()
                return
            m = RE_SETTHRESHOLD.match(message)
            if m is not None:
                self._update_variable('threshold', float(m.group('threshold')))
                self._update_variable('vcmp', float(m.group('vcmp')))
                self._update_variable('gain', m.group('gain'))
                self._update_variable('trimfile', m.group('trimfile'))
                return
            m = RE_SETTHRESHOLD_ACK.match(message)
            if m is not None:
                self._handle_end_trimming()
                return
            m = RE_IMGMODE.match(message)
            if m is not None:
                self._update_variable('imgmode', m.group('imgmode'))
                return
            if not message:
                # empty message
                return
            if status == b'ERR':
                raise DeviceError('Pilatus error: %s' % (message.decode('ascii')))
            raise DeviceError('Unknown message from Pilatus with idnum==15: %s' % origmessage)
        elif idnum == 16:
            m = RE_PID.match(message)
            if m is None:
                raise DeviceError('Unknown ShowPID message from Pilatus: %s' % origmessage)
            self._update_variable('pid', int(m.group('pid')))
        elif idnum == 18:  # telemetry
            m = RE_TELEMETRY.match(message)
            if m is None:
                raise DeviceError('Invalid telemetry message received: %s' % message)
            gd = m.groupdict()
            self._update_variable('wpix', int(gd['wpix']))
            self._update_variable('hpix', int(gd['hpix']))
            self._update_variable('sel_bank', int(gd['sel_bank']))
            self._update_variable('sel_module', int(gd['sel_module']))
            self._update_variable('sel_chip', int(gd['sel_chip']))
            self._update_variable('telemetry_date', dateutil.parser.parse(gd['telemetry_date']))
            self._update_variable('temperature0', float(gd['temperature0']))
            self._update_variable('temperature1', float(gd['temperature1']))
            self._update_variable('temperature2', float(gd['temperature2']))
            self._update_variable('humidity0', float(gd['humidity0']))
            self._update_variable('humidity1', float(gd['humidity1']))
            self._update_variable('humidity2', float(gd['humidity2']))
        elif idnum == 24:
            m = RE_VERSION.match(message)
            if m is None:
                raise DeviceError('Invalid version message received from Pilatus: %s' % origmessage)
            self._update_variable('version', m.group('version'))
        elif idnum == 215:
            m = RE_THREAD.match(message)
            if m is None:
                raise DeviceError('Invalid THread message received from Pilatus: %s' % origmessage)
            gd = m.groupdict()
            for k in gd:
                self._update_variable(k, float(gd[k]))
        else:
            raise DeviceError(
                'Unknown command ID in message from Pilatus: %s' % origmessage)

    def _execute_command(self, commandname: str, arguments: tuple) -> None:
        self._logger.debug('Executing command: %s(%s)' %
                           (commandname, repr(arguments)))
        if commandname == 'setthreshold':
#            if self.is_busy():
#                raise DeviceError('Cannot trim when not idle')
            self._update_variable('_status', 'trimming')
            self._suppress_watchdog()
            self._send(b'SetThreshold %s %f\n' % (arguments[1], arguments[0]), expected_replies=None)
            logger.debug('Setting threshold to %f (gain %s)' % (arguments[0], arguments[1]))
        elif commandname == 'expose':
#            if self.is_busy():
#                raise DeviceError('Cannot start exposure when not idle')
            self._send(b'Exposure ' + arguments[0] + b'\n', expected_replies=None)
            nimages = self._properties['nimages']
            exptime = self._properties['exptime']
            expdelay = self._properties['expperiod'] - exptime
            self._exposureendsat = time.time() + nimages * exptime + (nimages - 1) * expdelay
            if nimages == 1:
                self._expected_status = 'exposing'
                self._update_variable('_status', 'exposing')
                self._suppress_watchdog()
            else:
                self._expected_status = 'exposing multi'
                self._update_variable('_status', 'exposing multi')
                self._suppress_watchdog()
        elif commandname == 'kill':
            if self.get_variable('_status') == 'exposing':
                self._logger.debug('Killing single exposure')
                self._send(b'resetcam\n', expected_replies=None)
                self._exposureendsat = time.time() + 3
            elif self.get_variable('_status') == 'exposing multi':
                self._send(b'K\n', expected_replies=None)
                self._logger.debug('Killing multiple exposure')
                self._exposureendsat = time.time() + 3
            else:
                raise DeviceError('No running exposures to be killed')
        elif commandname == 'resetcam':
            self._send(b'resetcam\n', expected_replies=None)
        else:
            raise UnknownCommand(commandname)

    def _set_variable(self, variable: str, value: object):
        if variable == 'expperiod':
            if value < 1e-7:
                raise InvalidValue('Illegal exposure period: %f' % value)
            self._send(b'expperiod %f\n' % value, expected_replies=None)
        elif variable == 'nimages':
            if value < 1:
                raise InvalidValue('Illegal nimages: %d' % value)
            self._send(b'nimages %d\n' % value, expected_replies=None)
        elif variable == 'tau':
            if value < 0.1e-9 or value > 1000e-9:
                raise InvalidValue('Illegal tau: %f' % value)
            self._send(b'tau %f\n' % value, expected_replies=None)
        elif variable == 'imgpath':
            assert (isinstance(value, str))
            self._send(b'imgpath %s\n' % value.encode('utf-8'), expected_replies=None)
        elif variable == 'exptime':
            if value < 1e-7:
                raise InvalidValue('Illegal exposure time: %f' % value)
            self._send(b'exptime %f\n' % value, expected_replies=None)
        elif variable in self._all_variables:
            raise ReadOnlyVariable(variable)
        else:
            raise UnknownVariable(variable)

    def set_threshold(self, thresholdvalue: float, gain: str):
        if gain.upper() not in ['LOWG', 'MIDG', 'HIGHG']:
            raise ValueError(gain)
        if not self._busysemaphore.acquire(False):
            raise DeviceError('Cannot start trimming when not idle.')
        self.execute_command(
            'setthreshold', thresholdvalue, gain.encode('ascii'))
        logger.debug('Setting threshold to %f (gain %s)' % (thresholdvalue, gain))

    def expose(self, filename: str):
        if not self._busysemaphore.acquire(False):
            raise DeviceError('Cannot start exposure when not idle.')
        self.execute_command('expose', filename.encode('utf-8'))

    def do_startupdone(self):
        logger.debug('Pilatus: do_startupdone')
        self.refresh_variable('version')
        self.set_threshold(4024, 'highg')
        return super().do_startupdone()

    def _on_startupdone(self):
        self._update_variable('_status', 'idle')
        self._update_variable('starttime', None)
