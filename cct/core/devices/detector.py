import logging
import multiprocessing
import queue
import re
import time

import dateutil.parser

from .device import Device_TCP, DeviceError, ReadOnlyVariable, CommunicationError, UnknownVariable

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ToDo: killing exposure not working for multiple exposures

RE_FLOAT = br"[+-]?(\d+)*\.?\d+([eE][+-]?\d+)?"
RE_DATE = br"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+"
RE_INT = br"[+-]?\d+"

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
                    br"-" + RE_INT + br")\n\s*Camera state: (?P<camstate>.*)\n\s*Target file: (?P<targetfile>.*)\n\s*Time left: (?P<timeleft>" + RE_FLOAT +
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

    backend_interval = 0.5
    
    _minimum_query_variables = ['gain', 'trimfile', 'nimages', 'cameradef',
                                'imgpath', 'imgmode', 'PID', 'expperiod', 
                                'diskfree', 'tau']

    def __init__(self, *args, **kwargs):
        Device_TCP.__init__(self, *args, **kwargs)
        self._expected_status = 'idle'
        # a flag which has to be acquired when the detector is busy: trimming or exposing.
        self._busysemaphore=multiprocessing.BoundedSemaphore(1)

    def is_busy(self):
        return self._busysemaphore.get_value()==0

    def _query_variable(self, variablename, minimum_query_variables=None):
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
            self._send(b'SetThreshold\n')
        elif variablename in ['trimfile', 'wpix', 'hpix', 'sel_bank', 'sel_module', 'sel_chip']:
            self._send(b'Telemetry\n')
        elif variablename.startswith('humidity') or variablename.startswith('temperature'):
            self._send(b'THread\n')
        elif variablename == 'nimages':
            self._send(b'NImages\n')
        elif variablename in ['cameradef', 'cameraname', 'cameraSN', 'camstate', 'targetfile',
                    'timeleft', 'lastimage', 'masterPID', 'controllingPID',
                    'exptime', 'lastcompletedimage', 'shutterstate']:
            self._send(b'camsetup\n')
        elif variablename == 'imgpath':
            self._send(b'imgpath\n')
        elif variablename == 'imgmode':
            self._send(b'imgmode\n')
        elif variablename == 'PID':
            self._send(b'ShowPID\n')
        elif variablename == 'expperiod':
            self._send(b'expperiod\n')
        elif variablename in ['tau', 'cutoff']:
            self._send(b'tau\n')
        elif variablename == 'diskfree':
            self._send(b'df\n')
        elif variablename == 'version':
            self._send(b'version\n')
        else:
            raise UnknownVariable(variablename)

    def _get_complete_messages(self, message):
        return message.split(b'\x18')

    def _process_incoming_message(self, message, original_sent=None):
        self._pat_watchdog()
        try:
            # a safety measure to end the exposure if for some reason we miss the exposure end message.
            if time.time() > self._exposureendsat:
                self._update_variable('_status', 'idle')
                self._update_variable('starttime', None)
                self._release_watchdog()
                del self._exposureendsat
        except AttributeError:
            pass
        try:
            origmessage = message
            # self._logger.debug('Pilatus message received: %s' % str(message))
            try:
                if message.count(b' ') < 2:
                    # empty message, like '15 OK'
                    idnum, status = message.split(b' ') # this can raise ValueError, see below.
                    status = status[:-1]  # cut the b'\x18' from the end
                    message=''
                else:
                    idnum, status, message = message.split(b' ', 2)
                idnum = int(idnum)
            except ValueError:
                # recover. SetThreshold is known to send b'/tmp/setthreshold.cmd'
                # upon completion.
                idnum = -1
                status = b'OK'
            message = message.strip()
#            if status != b'OK':
#                try:
#                    raise DeviceError('Status of message is not "OK", but "%s": %s' % (
#                        status.decode('utf-8'), origmessage.decode('utf-8')))
#                except DeviceError as exc:
#                    self._send_to_frontend('error', exception=exc, traceback=sys.exc_info()[2], variablename=None)

            # handle special cases
            if message == b'/tmp/setthreshold.cmd':
                # a new threshold has been set, update the variables
                self._update_variable('_status', 'idle')
                self._query_variable('threshold')
                self._query_variable('tau')
            else:
                if idnum not in pilatus_replies_compiled:
                    raise DeviceError(
                        'Unknown command ID in message: %d %s %s (original: %s)' % (idnum, status, message, origmessage))
                if idnum == -1 and message == b'access denied':
                    raise CommunicationError(
                        'We could only connect to Pilatus in read-only mode')
                if idnum == 7:  # and status == b'OK':
                    # exposing finished, we can release the watchdog
                    self._update_variable('_status', 'idle')
                    self._update_variable('starttime',None)
                    self._release_watchdog()
                if idnum==13:
                    # killed
                    self._update_variable('_status', 'idle')
                    self._update_variable('starttime',None)
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
                                raise NotImplementedError(
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
        self._logger.debug('Executing command: %s(%s)' %
                     (commandname, repr(arguments)))
        if commandname == 'setthreshold':
            if self.get_variable('_status') != 'idle':
                raise DeviceError('Cannot trim when not idle')
            self._send(b'SetThreshold %s %f\n' % (arguments[1], arguments[0]))
            # after trimming, a camsetup call will reset this to idle.
            self._update_variable('_status', 'trimming')
            logger.debug('Setting threshold to %f (gain %s)' % (arguments[0], arguments[1]))
        elif commandname == 'expose':
            if self.get_variable('_status') != 'idle':
                raise DeviceError('Cannot start exposure when not idle')
            self._send(b'Exposure ' + arguments[0] + b'\n')
            nimages = self.get_variable('nimages')
            exptime = self.get_variable('exptime')
            expdelay = self.get_variable('expperiod') - exptime
            self._exposureendsat = time.time() + nimages * exptime + (nimages - 1) * expdelay
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
                self._logger.debug('Killing single exposure')
                self._send(b'K\nresetcam\n')
                self._exposureendsat=time.time()+3
            elif self.get_variable('_status') == 'exposing multi':
                self._send(b'K\nresetcam\n')
                self._logger.debug('Killing multiple exposure')
                self._exposureendsat=time.time()+3
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
            self._send(b'imgpath %s\n' % value.encode('utf-8'))
        elif variable == 'exptime':
            self._send(b'exptime %f\n' % value)
        else:
            raise ReadOnlyVariable(variable)

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
        logger.debug('Setting threshold to %f (gain %s)' % (thresholdvalue, gain))

    def expose(self, filename):
        self.execute_command('expose', filename.encode('utf-8'))

    def do_startupdone(self):
        self._logger.debug('Pilatus: do_startupdone')
        self.refresh_variable('version')
        self.set_threshold(4024, 'highg')
        Device_TCP.do_startupdone(self)
        return False

    def _initialize_after_connect(self):
        Device_TCP._initialize_after_connect(self)

    def _on_startupdone(self):
        self._update_variable('_status', 'idle')
        self._update_variable('starttime', None)
