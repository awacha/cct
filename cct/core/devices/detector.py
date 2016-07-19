import logging
import re
import time
from typing import Optional

import dateutil.parser

from .device import Device, DeviceError, ReadOnlyVariable, CommunicationError, UnknownVariable, InvalidValue, \
    UnknownCommand, DeviceBackend_TCP

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
    "Starting (?P<exptime>{float}) second background: (?P<starttime>{date})".format(float=RE_FLOAT,
                                                                                    date=RE_DATE).encode(
        'ascii'))

RE_SETTHRESHOLD = re.compile(
    """Settings: (?P<gain>[a-z]+) gain; threshold: (?P<threshold>{float}) eV; vcmp: (?P<vcmp>{float}) V
 Trim file:
  (?P<trimfile>.*)""".format(float=RE_FLOAT).encode('ascii'), re.MULTILINE)

RE_SETTHRESHOLD_ACK = re.compile(b'/tmp/setthreshold.cmd')

RE_IMGMODE = re.compile(
    """ImgMode is (?P<imgmode>.+)""".encode('ascii')
)

RE_SETLIMTH = re.compile(
    """chan\s+Tlo\s+Thi\s+Hlo\s+Hhi\s*
\s*{i}\s+(?P<limtemp_lo0>{f})\s+(?P<limtemp_hi0>{f})\s+(?P<limhum_lo0>{f})\s+(?P<limhum_hi0>{f})\s*
\s*{i}\s+(?P<limtemp_lo1>{f})\s+(?P<limtemp_hi1>{f})\s+(?P<limhum_lo1>{f})\s+(?P<limhum_hi1>{f})\s*
\s*{i}\s+(?P<limtemp_lo2>{f})\s+(?P<limtemp_hi2>{f})\s+(?P<limhum_lo2>{f})\s+(?P<limhum_hi2>{f})""".format(
        i=RE_INT, f=RE_FLOAT).encode('ascii'), re.MULTILINE
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


class Pilatus_Backend(DeviceBackend_TCP):
    idle_wait = 1.0
    
    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self._expected_status = 'idle'
        # a flag which has to be acquired when the detector is busy: trimming or exposing.

    def queryall(self):
        if self.is_busy():
            # do not initiate query-all-variables if we are exposing or 
            # trimming: the pilatus detector is known to become unresponsive
            # during these times.
            return
        elif ((self.properties['_status'] == 'idle') and (
            time.monotonic() - self.timestamps['_status']) < self.idle_wait):
            # if the previous exposure has just finished, wait a little,
            # in case we are in a scan and want to start another exposure
            # shortly.
            return
        else:
            super().queryall()

    def query_variable(self, variablename: str) -> bool:
        if variablename in ['gain', 'threshold', 'vcmp']:
            self.send_message(b'SetThreshold\n', expected_replies=1, asynchronous=False)
        elif variablename in ['trimfile', 'wpix', 'hpix', 'sel_bank', 'sel_module', 'sel_chip']:
            self.send_message(b'Telemetry\n', expected_replies=1, asynchronous=False)
        elif variablename.startswith('humidity') or variablename.startswith('temperature'):
            self.send_message(b'THread\n', expected_replies=1, asynchronous=False)
        elif variablename == 'nimages':
            self.send_message(b'NImages\n', expected_replies=1, asynchronous=False)
        elif variablename in ['cameradef', 'cameraname', 'cameraSN', 'camstate', 'targetfile',
                              'timeleft', 'lastimage', 'masterPID', 'controllingPID',
                              'exptime', 'lastcompletedimage', 'shutterstate']:
            self.send_message(b'camsetup\n', expected_replies=1, asynchronous=False)
        elif variablename in ['limtemp_lo0', 'limtemp_lo1', 'limtemp_lo2',
                              'limtemp_hi0', 'limtemp_hi1', 'limtemp_hi2',
                              'limhum_lo0', 'limhum_lo1', 'limhum_lo2',
                              'limhum_hi0', 'limhum_hi1', 'limhum_hi2']:
            self.send_message(b'setlimth\n', expected_replies=1, asynchronous=False)
        elif variablename == 'imgpath':
            self.send_message(b'imgpath\n', expected_replies=1, asynchronous=False)
        elif variablename == 'imgmode':
            self.send_message(b'imgmode\n', expected_replies=1, asynchronous=False)
        elif variablename == 'pid':
            self.send_message(b'ShowPID\n', expected_replies=1, asynchronous=False)
        elif variablename == 'expperiod':
            self.send_message(b'expperiod\n', expected_replies=1, asynchronous=False)
        elif variablename in ['tau', 'cutoff']:
            self.send_message(b'tau\n', expected_replies=1, asynchronous=False)
        elif variablename == 'diskfree':
            self.send_message(b'df\n', expected_replies=1, asynchronous=False)
        elif variablename == 'version':
            self.send_message(b'version\n', expected_replies=1, asynchronous=False)
        elif variablename == 'starttime':
            if not self.is_busy():
                self.update_variable('starttime', None)
            else:
                # starttime has already been set
                pass
            return False

        elif variablename == 'filename':
            if not self.is_busy():
                self.update_variable('filename', 'lastimage')
            return False
        else:
            raise UnknownVariable(variablename)
        return True

    @staticmethod
    def get_complete_messages(message: bytes) -> list:
        return message.split(b'\x18')

    def on_end_exposure(self, status: bool, message: bytes) -> None:
        self.logger.debug('Exposure ended.')
        try:
            self.busysemaphore.release()
        except ValueError:
            return
        self.update_variable('_status', 'idle')
        self.update_variable('lastimage', message.decode('utf-8'))
        self.update_variable('filename', message.decode('utf-8'))
        self.update_variable('starttime', None)
        if status:
            self.update_variable('lastcompletedimage', message.decode('utf-8'))
        self.watchdog.enable()

    def on_end_trimming(self) -> None:
        # a new threshold has been set, update the variables
        try:
            self.busysemaphore.release()
        except ValueError:
            return
        self.update_variable('_status', 'idle')
        self.query_variable('threshold')
        self.query_variable('tau')
        self.watchdog.enable()

    def on_start_exposure(self) -> None:
        self.update_variable('_status', self._expected_status)

    def process_incoming_message(self, message: bytes, original_sent: Optional[bytes] = None) -> None:
        origmessage = message
        # Messages from the Pilatus detector generally have the following
        #   format:
        #
        # <ID><space>(OK|ERR)<space>[<message>]
        #
        # where:
        #   - ID is a positive integer related to the issued command to which
        #        this is a reply,
        #   - the status code is either OK or ERR,
        #   - the message is dependent on the command, and can be omitted.
        #
        # In some cases this format is not followed, e.g.
        # b'/tmp/setthreshold.cmd' is a typical response to the SetThreshold
        # command.
        #

        if b'' not in message:
            # e.g. b'/tmp/setthreshold.cmd'
            idnum = b'15'
            status = b'OK'
        elif message.count(b' ') == 1:
            # empty message, like '15 OK'
            idnum, status = message.split(b' ')
            message = b''
        else:
            idnum, status, message = message.split(b' ', 2)
        idnum = int(idnum)
        message = message.strip()
        # handle cases based on the message ID
        if idnum == 1:  # happens when b'1 ERR access denied'
            # access denied
            if (message == b'access denied') and (status == b'ERR'):
                raise CommunicationError(
                    'We could only connect to Pilatus in read-only mode')
            else:
                raise DeviceError('Unknown message received from Pilatus: ' + origmessage.decode('utf-8'))
        elif idnum == 2:  # reply to command 'camsetup'
            m = RE_CAMSETUP.match(message)
            if m is None:
                raise DeviceError('Invalid camsetup message from Pilatus: ' + origmessage.decode('utf-8'))
            gd = m.groupdict()
            for k in ['controllingPID', 'masterPID']:
                gd[k] = int(gd[k])
            for k in ['exptime', 'timeleft']:
                gd[k] = float(gd[k])
            for k in [k_ for k_ in gd if k_ not in ['controllingPID', 'masterPID', 'exptime', 'timeleft']]:
                gd[k] = gd[k].decode('utf-8')
            for k in gd:
                self.update_variable(k, gd[k])
        elif idnum == 5:  # reply to command 'df'
            m = RE_DISKFREE.match(message)
            if m is None:
                raise DeviceError('Invalid diskfree message from Pilatus: ' + origmessage.decode('utf-8'))
            self.update_variable('diskfree', int(m.group('diskfree')))
        elif idnum == 7:  # 2nd reply to command 'exposure', at the end.
            # end of exposure
            self.on_end_exposure(status == b'OK', message)
        elif idnum == 10:  # reply to command 'imgpath'
            m = RE_IMGPATH.match(message)
            if m is None:
                raise DeviceError('Invalid imgpath message from Pilatus: ' + origmessage.decode('utf-8'))
            self.update_variable('imgpath', m.group('imgpath').decode('utf-8'))
        elif idnum == 13:  # reply to command 'K'
            # killed
            m = RE_KILL.match(message)
            if m is None:
                raise DeviceError('Unknown kill message from Pilatus: ' + origmessage.decode('utf-8'))
            self.on_end_exposure(status == b'OK', b'')
        elif idnum == 15:  # several commands respond with idnum==15, check all.
            for regex in [RE_EXPTIME, RE_EXPPERIOD, RE_TAU_ON, RE_TAU_SETON, RE_TAU_SETOFF, RE_TAU_OFF, RE_NIMAGES,
                          RE_EXPSTART, RE_SETTHRESHOLD, RE_SETTHRESHOLD_ACK, RE_IMGMODE]:
                m = regex.match(message)
                if m is None:
                    continue
                for var, conversion in [('exptime', float), ('expperiod', float),
                                        ('tau', float), ('cutoff', float),
                                        ('nimages', float),
                                        ('starttime', lambda x: dateutil.parser.parse(x.decode('utf-8'))),
                                        ('threshold', float), ('vcmp', float),
                                        ('gain', lambda x: x.decode('utf-8')),
                                        ('trimfile', lambda x: x.decode('utf-8')),
                                        ('imgmode', lambda x: x.decode('utf-8'))]:
                    try:
                        self.update_variable(var, conversion(m.group(var)))
                    except IndexError:
                        continue
                if regex is RE_EXPSTART:
                    self.on_start_exposure()
                if regex is RE_SETTHRESHOLD_ACK:
                    self.on_end_trimming()
                break  # do not try matching other regexes after one was matched successfully.
            if status == b'ERR':
                raise DeviceError('Pilatus error: ' + message.decode('utf-8'))
            elif not message:
                # empty message
                pass
            else:
                raise DeviceError('Unknown message from Pilatus with idnum==15: ' + origmessage.decode('utf-8'))
        elif idnum == 16:  # return of ShowPID command.
            m = RE_PID.match(message)
            if m is None:
                raise DeviceError('Unknown ShowPID message from Pilatus: ' + origmessage.decode('utf-8'))
            self.update_variable('pid', int(m.group('pid')))
        elif idnum == 18:  # telemetry
            m = RE_TELEMETRY.match(message)
            if m is None:
                raise DeviceError('Invalid telemetry message received: ' + message.decode('utf-8'))
            gd = m.groupdict()
            self.update_variable('wpix', int(gd['wpix']))
            self.update_variable('hpix', int(gd['hpix']))
            self.update_variable('sel_bank', int(gd['sel_bank']))
            self.update_variable('sel_module', int(gd['sel_module']))
            self.update_variable('sel_chip', int(gd['sel_chip']))
            self.update_variable('telemetry_date', dateutil.parser.parse(gd['telemetry_date'].decode('utf-8')))
            self.update_variable('temperature0', float(gd['temperature0']))
            self.update_variable('temperature1', float(gd['temperature1']))
            self.update_variable('temperature2', float(gd['temperature2']))
            self.update_variable('humidity0', float(gd['humidity0']))
            self.update_variable('humidity1', float(gd['humidity1']))
            self.update_variable('humidity2', float(gd['humidity2']))
        elif idnum == 24:  # reply for command 'version'
            m = RE_VERSION.match(message)
            if m is None:
                raise DeviceError('Invalid version message received from Pilatus: ' + origmessage.decode('utf-8'))
            self.update_variable('version', m.group('version').decode('utf-8'))
        elif idnum == 215:  # reply for command 'thread'
            m = RE_THREAD.match(message)
            if m is None:
                raise DeviceError('Invalid THread message received from Pilatus: ' + origmessage.decode('utf-8'))
            gd = m.groupdict()
            for k in gd:
                self.update_variable(k, float(gd[k]))
        else:
            raise DeviceError(
                'Unknown command ID in message from Pilatus: ' + origmessage.decode('utf-8'))

    def execute_command(self, commandname: str, arguments: tuple) -> None:
        self.logger.debug('Executing command: {}({})'.format(commandname, repr(arguments)))
        if commandname == 'setthreshold':
            #            if self.is_busy():
            #                raise DeviceError('Cannot trim when not idle')
            self.update_variable('_status', 'trimming')
            self.watchdog.disable()
            self.send_message(
                'SetThreshold {} {:f}\n'.format(arguments[1].decode('ascii'), arguments[0]).encode('ascii'),
                expected_replies=1, asynchronous=False)
            logger.debug('Setting threshold to {0[0]:f} (gain {0[1]})'.format(arguments))
        elif commandname == 'expose':
            #            if self.is_busy():
            #                raise DeviceError('Cannot start exposure when not idle')
            nimages = self.properties['nimages']
            exptime = self.properties['exptime']
            expdelay = self.properties['expperiod'] - exptime
            timeout = nimages * exptime + (nimages - 1) * expdelay
            self.send_message(b'Exposure ' + arguments[0] + b'\n', expected_replies=2, asynchronous=False,
                              timeout=timeout + 60)
            self._exposureendsat = time.monotonic() + timeout
            if nimages == 1:
                self._expected_status = 'exposing'
                self.update_variable('_status', 'exposing')
            else:
                self._expected_status = 'exposing multi'
                self.update_variable('_status', 'exposing multi')
            self.watchdog.disable()
        elif commandname == 'kill':
            if self.properties['_status'] == 'exposing':
                self.logger.debug('Killing single exposure')
                self.send_message(b'resetcam\n', expected_replies=1, asynchronous=False)
                self._exposureendsat = time.monotonic() + 3
            elif self.properties['_status'] == 'exposing multi':
                self.send_message(b'K\n', expected_replies=1, asynchronous=False)
                self.logger.debug('Killing multiple exposure')
                self._exposureendsat = time.monotonic() + 3
            else:
                raise DeviceError('No running exposures to be killed')
        elif commandname == 'resetcam':
            self.send_message(b'resetcam\n', expected_replies=1, asynchronous=False)
        else:
            raise UnknownCommand(commandname)

    def set_variable(self, variable: str, value: object):
        if variable == 'expperiod':
            if value < 1e-7:
                raise InvalidValue('Illegal exposure period: {:f}'.format(value))
            self.send_message('expperiod {:f}\n'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'nimages':
            if value < 1:
                raise InvalidValue('Illegal nimages: {:d}'.format(value))
            self.send_message('nimages {:d}\n'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'tau':
            if value < 0.1e-9 or value > 1000e-9:
                raise InvalidValue('Illegal tau: {:f}'.format(value))
            self.send_message('tau {:f}\n'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'imgpath':
            assert (isinstance(value, str))
            self.send_message('imgpath {}\n'.format(value).encode('utf-8'), expected_replies=1, asynchronous=False)
        elif variable == 'exptime':
            if value < 1e-7:
                raise InvalidValue('Illegal exposure time: {:f}'.format(value))
            self.send_message('exptime {:f}\n'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable in self.all_variables:
            raise ReadOnlyVariable(variable)
        else:
            raise UnknownVariable(variable)

    def on_startupdone(self):
        self.update_variable('_status', 'idle')

class Pilatus(Device):
    log_formatstr = '{_status}\t{exptime}\t{humidity0}\t{humidity1}\t{humidity2}\t{temperature0}\t{temperature1}\t{temperature2}'

    watchdog_timeout = 20

    reply_timeout = 20

    idle_wait = 2

    minimum_query_variables = ['gain', 'trimfile', 'nimages', 'cameradef',
                               'imgpath', 'imgmode', 'pid', 'expperiod',
                               'diskfree', 'tau', 'limtemp_lo0']

    all_variables = ['gain', 'threshold', 'vcmp', 'trimfile', 'wpix', 'hpix',
                     'sel_bank', 'sel_module', 'sel_chip', 'humidity0',
                     'humidity1', 'humidity2', 'temperature0', 'temperature1',
                     'temperature2', 'nimages', 'cameradef', 'cameraname',
                     'cameraSN', 'camstate', 'targetfile', 'timeleft',
                     'lastimage', 'masterPID', 'controllingPID', 'exptime',
                     'lastcompletedimage', 'shutterstate', 'imgpath',
                     'imgmode', 'pid', 'expperiod', 'tau', 'cutoff',
                     'diskfree', 'version', 'telemetry_date',
                     'limtemp_lo0', 'limtemp_lo1', 'limtemp_lo2',
                     'limtemp_hi0', 'limtemp_hi1', 'limtemp_hi2',
                     'limhum_lo0', 'limhum_lo1', 'limhum_lo2',
                     'limhum_hi0', 'limhum_hi1', 'limhum_hi2',
                     ]

    constant_variables = ['wpix', 'hpix', 'cameradef', 'cameraname',
                          'cameraSN', 'masterPID', 'controllingPID',
                          'pid', 'version']

    backend_class = Pilatus_Backend

    def set_threshold(self, thresholdvalue: float, gain: str):
        if gain.upper() not in ['LOWG', 'MIDG', 'HIGHG']:
            raise ValueError(gain)
        if not self._busy.acquire(False):
            raise DeviceError('Cannot start trimming when not idle.')
        self.execute_command(
            'setthreshold', thresholdvalue, gain.encode('ascii'))
        logger.debug('Setting threshold to {:f} (gain {})'.format(thresholdvalue, gain))

    def expose(self, filename: str):
        if not self._busy.acquire(False):
            raise DeviceError('Cannot start exposure when not idle.')
        self.execute_command('expose', filename.encode('utf-8'))

    def do_startupdone(self):
        logger.debug('Pilatus: do_startupdone')
        self.refresh_variable('version')
        self.set_threshold(4024, 'highg')
        return super().do_startupdone()
