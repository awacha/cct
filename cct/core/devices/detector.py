import logging
import traceback
import multiprocessing
import queue
import re

import dateutil.parser

from .device import Device_TCP, DeviceError, CommunicationError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ToDo: killing exposure not working for multiple exposures

RE_FLOAT = br"[+-]?(\d+)*\.?\d+([eE][+-]?\d+)?"
RE_DATE = br"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+"
RE_INT = br"[+-]?\d+"

pilatus_int_variables = ['wpix', 'hpix', 'sel_bank', 'sel_module',
                         'sel_chip', 'diskfree', 'nimages', 'masterPID', 'controllingPID', 'pid']
pilatus_float_variables = ['tau', 'cutoff', 'exptime', 'expperiod', 'temperature0',
                           'temperature1', 'temperature2', 'humidity0', 'humidity1', 'humidity2', 'threshold', 'vcmp', 'timeleft',
                           'exptime']
pilatus_date_variables = ['starttime']
pilatus_str_variables = ['version', 'gain', 'trimfile', 'cameradef', 'cameraname', 'cameraSN', '_status', 'targetfile',
                         'lastimage', 'lastcompletedimage', 'shutterstate', 'imgpath', 'imgmode', 'filename']

pilatus_replies = [(15, br'Rate correction is on; tau = (?P<tau>' + RE_FLOAT +
                    br') s, cutoff = (?P<cutoff>' + RE_INT + br') counts'),
                   (15, br'Rate correction is off, cutoff = (?P<cutoff>' +
                    RE_INT + br') counts'),
                   (15, br'Set up rate correction: tau = (?P<tau>' +
                    RE_FLOAT + br') s'),
                   (15, br'Exposure time set to: (?P<exptime>' +
                    RE_FLOAT + br') sec.'),
                   (15, br'Exposure period set to: (?P<expperiod>' + RE_FLOAT +
                    br') sec'),
                   (15, br'Illegal exposure period'),
                   (15, br'Starting (?P<exptime>' + RE_FLOAT +
                    br') second background: (?P<starttime>' + RE_DATE + br')'),
                   (7, br'(?P<filename>.*)'),
                   (24, br'Code release:\s*(?P<version>.*)'),
                   (18, br'=== Telemetry at ' + RE_DATE +
                    br' ===\s*\nImage format: (?P<wpix>' + RE_INT +
                    br')\(w\) x (?P<hpix>' + RE_INT +
                    br')\(h\) pixels\s*\nSelected bank: (?P<sel_bank>' +
                    RE_INT + br')\s*\nSelected module: (?P<sel_module>' +
                    RE_INT + br')\s*\nSelected chip: (?P<sel_chip>' + RE_INT +
                    br')\s*\nChannel ' + RE_INT + br': Temperature = (?P<temperature0>' +
                    RE_FLOAT + br')C, Rel. Humidity = (?P<humidity0>' + RE_FLOAT +
                    br')%\s*\nChannel ' + RE_INT + br': Temperature = (?P<temperature1>' +
                    RE_FLOAT + br')C, Rel. Humidity = (?P<humidity1>' + RE_FLOAT +
                    br')%\s*\nChannel ' + RE_INT + br': Temperature = (?P<temperature2>' +
                    RE_FLOAT + br')C, Rel. Humidity = (?P<humidity2>' + RE_FLOAT +
                    br')%\s*'),
                   (5, br'(?P<diskfree>' + RE_INT + b')'),
                   (15, b'Settings: (?P<gain>\w+) gain; threshold: (?P<threshold>' + RE_INT +
                    b') eV; vcmp: (?P<vcmp>' + RE_FLOAT + b') V\n\s*Trim file:\s*\n\s*(?P<trimfile>.*)'),
                   (15, b'/tmp/setthreshold\.cmd'),
                   (15, b'Threshold has not been set'),
                   (15, b'Requested threshold \(' +
                    RE_FLOAT + b' eV\) is out of range',),
                   (13, b'kill'),
                   (15, b'N images set to: (?P<nimages>' + RE_INT + b')'),
                   (2, br"\n*\s*Camera definition:\n\s+(?P<cameradef>.*)\n\s*Camera name: (?P<cameraname>.*),\sS/N\s(?P<cameraSN>" + RE_INT +
                    br"-" + RE_INT + br")\n\s*Camera state: (?P<_status>.*)\n\s*Target file: (?P<targetfile>.*)\n\s*Time left: (?P<timeleft>" + RE_FLOAT +
                    br')\n\s*Last image: (?P<lastimage>.*)\n\s*Master PID is: (?P<masterPID>' + RE_INT +
                    br')\n\s*Controlling PID is: (?P<controllingPID>' + RE_INT +
                    br')\n\s*Exposure time: (?P<exptime>' + RE_FLOAT +
                    br')\n\s*Last completed image:\s*\n\s*(?P<lastcompletedimage>.*)\n\s*Shutter is: (?P<shutterstate>.*)\n*'),
                   (10, b'(?P<imgpath>.*)'),
                   (15, b'ImgMode is (?P<imgmode>.*)'),
                   (16, b'PID = (?P<pid>' + RE_INT + b')'),
                   (-1, b'access denied'),
                   (1, b'access denied'),
                   (-1, b'/tmp/setthreshold.cmd'),
                   (-1, br'(?P<filename>/home/det/p2_det/images/.*)'),
                   (-1, br'(?P<filename>/disk2/images/.*)'),
                   (15, br''),
                   ]

pilatus_replies_compiled = {}
for idnum in {r[0] for r in pilatus_replies}:
    pilatus_replies_compiled[idnum] = [
        re.compile(r[1], re.MULTILINE) for r in pilatus_replies if r[0] == idnum]


class Pilatus(Device_TCP):
    log_formatstr = '{_status}\t{exptime}\t{humidity0}\t{humidity1}\t{humidity2}\t{temperature0}\t{temperature1}\t{temperature2}'

    watchdog_timeout = 20

    def __init__(self, *args, **kwargs):
        Device_TCP.__init__(self, *args, **kwargs)
        self._sendqueue = multiprocessing.Queue()
        self._expected_status = 'idle'

    def _query_variable(self, variablename):
        if variablename is None:
            variablenames = ['gain', 'trimfile', 'nimages',
                             'cameradef', 'imgpath', 'imgmode', 'PID', 'expperiod', 'diskfree']
        else:
            variablenames = [variablename]

        for vn in variablenames:
            if vn in ['gain', 'threshold', 'vcmp']:
                self._send(b'SetThreshold\n')
            elif vn in ['trimfile', 'wpix', 'hpix', 'sel_bank', 'sel_module', 'sel_chip']:
                self._send(b'Telemetry\n')
            elif vn.startswith('humidity') or vn.startswith('temperature'):
                self._send(b'THread\n')
            elif vn == 'nimages':
                self._send(b'NImages\n')
            elif vn in ['cameradef', 'cameraname', 'cameraSN', '_status', 'targetfile',
                        'timeleft', 'lastimage', 'masterPID', 'controllingPID',
                        'exptime', 'lastcompletedimage', 'shutterstate']:
                self._send(b'camsetup\n')
            elif vn == 'imgpath':
                self._send(b'imgpath\n')
            elif vn == 'imgmode':
                self._send(b'imgmode\n')
            elif vn == 'PID':
                self._send(b'ShowPID\n')
            elif vn == 'expperiod':
                self._send(b'expperiod\n')
            elif vn in ['tau', 'cutoff']:
                self._send(b'tau\n')
            elif vn == 'diskfree':
                self._send(b'df\n')
            else:
                raise NotImplementedError(vn)

    def _process_incoming_message(self, message):
        try:
            origmessage = message
            #logger.debug('Pilatus message received: %s' % str(message))
            try:
                if message.count(b' ') < 2:
                    idnum, status = message.split(b' ')
                    status = status[:-1]  # cut the b'\x18' from the end
                    message = b'\x18'
                else:
                    idnum, status, message = message.split(b' ', 2)
                idnum = int(idnum)
            except ValueError:
                # recover. SetThreshold is known to send b'/tmp/setthreshold.cmd'
                # upon completion.
                idnum = -1
                status = b'OK'
                if not message.endswith(b'\x18'):
                    message = message + b'\x18'
            message = message.strip()
            if not message.endswith(b'\x18'):
                raise DeviceError(
                    'Invalid message (does not end with \\x18): %s' % str(message))
            message = message[:-1]
            if b'\x18' in message:
                #logger.warning('Multipart message: %s' % message)
                for m in message.split(b'\x18'):
                    self._process_incoming_message(m.strip() + b'\x18')
                return
            if status != b'OK':
                try:
                    raise DeviceError('Status of message is not "OK", but "%s": %s' % (
                    status.decode('utf-8'), origmessage.decode('utf-8')))
                except DeviceError as exc:
                    self._queue_to_frontend.put_nowait(
                        ('_error', (exc, traceback.format_exc())))

            # handle special cases
            if message == b'/tmp/setthreshold.cmd':
                # a new threshold has been set, update the variables
                self._update_variable('_status', 'idle')
                self._send(b'SetThreshold\n')
            else:
                if idnum not in pilatus_replies_compiled:
                    raise DeviceError(
                        'Unknown command ID in message: %d %s %s (original: %s)' % (idnum, status, message, origmessage))
                if idnum == -1 and message == b'access denied':
                    try:
                        raise CommunicationError(
                            'We could only connect to Pilatus in read-only mode')
                    except CommunicationError as exc:
                        self._queue_to_frontend.put_nowait(
                            ('_error', (exc, traceback.format_exc())))
                        return
                if idnum == 7 and status == b'OK':
                    # exposing finished, we can release the watchdog
                    self._release_watchdog()
                if idnum == 15 and message.startswith(b'Starting'):
                    self._update_variable('_status', self._expected_status)
                for r in pilatus_replies_compiled[idnum]:
                    m = r.match(message.strip())
                    if m is None:
                        continue
                    gd = m.groupdict()
                    for k in gd:
                        try:
                            if k in pilatus_float_variables:
                                converter = float
                            elif k in pilatus_int_variables:
                                converter = int
                            elif k in pilatus_str_variables:
                                converter = lambda x: x.decode('utf-8')
                            elif k in pilatus_date_variables:
                                converter = dateutil.parser.parse
                            else:
                                NotImplementedError(
                                    'Unknown converter for variable ' + str(k))
                            self._update_variable(k, converter(gd[k]))
                        except:
                            raise DeviceError('Error updating variable %s' % k)
                    return
                raise DeviceError('Cannot decode message: "%d" "%s" "%s"' %
                                  (idnum, status, message))
        finally:
            try:
                msg = self._sendqueue.get_nowait()
                self._lastsent = msg
                Device_TCP._send(self, msg)
            except queue.Empty:
                try:
                    del self._lastsent
                except AttributeError:
                    pass

    def _execute_command(self, commandname, arguments):
        logger.debug('Executing command: %s(%s)' %
                     (commandname, repr(arguments)))
        if commandname == 'setthreshold':
            if self.get_variable('_status') != 'idle':
                raise DeviceError('Cannot trim when not idle')
            self._send(b'SetThreshold %f %s\n' % (arguments[0], arguments[1]))
            # after trimming, a camsetup call will reset this to idle.
            self._update_variable('_status', 'trimming')
        elif commandname == 'expose':
            if self.get_variable('_status') != 'idle':
                raise DeviceError('Cannot start exposure when not idle')
            self._send(b'Exposure ' + arguments[0] + b'\n')
            if self.get_variable('nimages') == 1:
                self._expected_status = 'exposing'
                self._update_variable('_status', 'exposing')
                self._suppress_watchdog()
            else:
                self._expected_status = 'exposing multi'
                self._update_variable('_status', 'exposing multi')
                self._suppress_watchdog()
        elif commandname == 'kill':
            if self.get_variable('_status') == 'exposing':
                logger.debug('Killing single exposure')
                self._send(b'K\nresetcam\n')
            elif self.get_variable('_status') == 'exposing multi':
                self._send(b'K\nresetcam\n')
                logger.debug('Killing multiple exposure')
            else:
                raise DeviceError('No running exposures to be killed')
            self._release_watchdog()
        elif commandname == 'resetcam':
            self._send(b'resetcam\n')
        else:
            raise NotImplementedError(commandname)

    def _set_variable(self, variable, value):
        if variable == 'expperiod':
            self._send(b'expperiod %f\n' % value)
        elif variable == 'nimages':
            self._send(b'nimages %d\n' % value)
        elif variable == 'tau':
            self._send(b'tau %f\n' % value)
        elif variable == 'imgpath':
            self._send(b'imgpath %s\n' % value)
        elif variable == 'exptime':
            self._send(b'exptime %f\n' % value)
        else:
            raise NotImplementedError(variable)

    def _send(self, message, dont_expect_reply=False):
        if hasattr(self, '_lastsent'):
            self._sendqueue.put_nowait(message)
            return
        self._lastsent = message
        Device_TCP._send(self, message)

    def set_threshold(self, thresholdvalue, gain):
        if gain.upper() not in ['LOWG', 'MIDG', 'HIGHG']:
            raise NotImplementedError(gain)
        self.execute_command(
            'setthreshold', thresholdvalue, gain.encode('utf-8'))

    def expose(self, filename):
        self.execute_command('expose', filename.encode('utf-8'))

    def do_startupdone(self):
        self.set_threshold(4024, 'highg')
        Device_TCP.do_startupdone(self)
        return False

    def _initialize_after_connect(self):
        Device_TCP._initialize_after_connect(self)
