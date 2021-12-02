import re
from math import inf
from typing import Sequence, Any, Tuple, List, Union

import dateutil.parser

from ...device.backend import DeviceBackend


class PilatusBackend(DeviceBackend):
    class Status:
        Idle = 'idle'
        Trimming = 'trimming'
        Exposing = 'exposing'
        ExposingMulti = 'exposing multiple images'
        Stopping = 'stopping exposure'

    varinfo = [
        DeviceBackend.VariableInfo(name='gain', dependsfrom=['threshold'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='threshold', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='vcmp', dependsfrom=['threshold'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='trimfile', dependsfrom=['telemetry_date'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='wpix', dependsfrom=['telemetry_date'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='hpix', dependsfrom=['telemetry_date'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='sel_bank', dependsfrom=['telemetry_date'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='sel_module', dependsfrom=['telemetry_date'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='sel_chip', dependsfrom=['telemetry_date'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='telemetry_date', dependsfrom=[], urgent=False, timeout=2),
        DeviceBackend.VariableInfo(name='humidity', dependsfrom=['temperature'], urgent=False, timeout=10),
        DeviceBackend.VariableInfo(name='temperature', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='nimages', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='cameradef', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='cameraname', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='cameraSN', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='camstate', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='targetfile', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='timeleft', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='lastimage', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='masterPID', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='controllingPID', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='exptime', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='lastcompletedimage', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='shutterstate', dependsfrom=['cameradef'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='temperaturelimits', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='humiditylimits', dependsfrom=['temperaturelimits'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='imgpath', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='imgmode', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='pid', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='expperiod', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='tau', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='cutoff', dependsfrom=['tau'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='diskfree', dependsfrom=[], urgent=False, timeout=2),
        DeviceBackend.VariableInfo(name='version', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='starttime', dependsfrom=[], urgent=False, timeout=inf),
        #        DeviceBackend.VariableInfo(name='filename', dependsfrom=[], urgent=False, timeout=inf),
    ]

    minimal_exposure_delay = 0.003  # seconds
    baseimagepath: str = None

    def _query(self, variablename: str):
        if variablename == 'threshold':
            self.enqueueHardwareMessage(b'SetThreshold\r')
        elif variablename == 'telemetry_date':
            self.enqueueHardwareMessage(b'Telemetry\r')
        elif variablename == 'temperature':
            self.enqueueHardwareMessage(b'THread\r')
        elif variablename == 'nimages':
            self.enqueueHardwareMessage(b'NImages\r')
        elif variablename == 'cameradef':
            self.enqueueHardwareMessage(b'camsetup\r')
        elif variablename == 'temperaturelimits':
            self.enqueueHardwareMessage(b'setlimth\r')
        elif variablename == 'imgpath':
            self.enqueueHardwareMessage(b'imgpath\r')
        elif variablename == 'imgmode':
            self.enqueueHardwareMessage(b'imgmode\r')
        elif variablename == 'pid':
            self.enqueueHardwareMessage(b'ShowPID\r')
        elif variablename == 'expperiod':
            self.enqueueHardwareMessage(b'expperiod\r')
        elif variablename == 'tau':
            self.enqueueHardwareMessage(b'tau\r')
        elif variablename == 'diskfree':
            self.enqueueHardwareMessage(b'df\r')
        elif variablename == 'version':
            self.enqueueHardwareMessage(b'version\r')
        elif variablename == 'starttime':
            if self['__status__'] not in [self.Status.Exposing, self.Status.ExposingMulti]:
                self.updateVariable('starttime', None)
        else:
            raise ValueError(f'Cannot query variable {variablename}')

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        messages = message.split(b'\x18')
        return messages[:-1], messages[-1]

    @staticmethod
    def _interpretTHline(line: Union[str, bytes]) -> Tuple[int, float, float]:
        if isinstance(line, bytes):
            line = line.decode('ascii')
        assert isinstance(line, str)
        m = re.match(r'^Channel (?P<channel>\d+):'
                     r' Temperature = (?P<temperature>[+-]?\d+\.\d+)C, '
                     r'Rel\. Humidity = (?P<humidity>\d+\.\d+)%;?$', line)
        if not m:
            raise ValueError(f'Invalid temperature/humidity line: {line}')
        return int(m['channel']), float(m['temperature']), float(m['humidity'])

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        # messages from the detector look like:
        # "<number> <OK|ERR> <remainder of the message>\x18"
        # where <number> is a function number, OK or ERR signifies if everything is OK or not.
        #
        # In some cases, the detector control software deviates from this, probably due to a bug. We work this around.
        if message.startswith(b'/'):
            # e.g. b'/tmp/setthreshold.cmd' is a typical response for the SetThreshold command
            idnum = b'15'
            status = b'OK'
            remainder = message
            self.messagereplytimeout = 1
        elif message.count(b' ') == 1:
            # empty message, e.g. b'15 OK'
            idnum, status = message.split(b' ')
            remainder = b''
        else:
            idnum, status, remainder = message.split(b' ', 2)
        idnum = int(idnum)
        status = status.decode('ascii')
        remainder = remainder.strip().decode('ascii')
        if (status == 'ERR') and (idnum == 13):
            # ERR kill, if a multiple exposure has been interrupted. This always sends a "7 OK <image file name>",
            # even if we interrupted during the exposure of the first image, so we don't need to do anything about
            # it.
            pass
        elif (status == 'ERR') and (idnum == 7):
            # Error in single exposure. We must put the device into idle state
            if (self['__status__'] == self.Status.Stopping) and (sentmessage == b'resetcam\r'):
                # an user break. Resetcam always returns a '15 OK' message, we re-trim the detector there.
                pass
            else:
                # not a user break, something went really wrong with the exposure
                self.debug(f'__status__=={self["__status__"]}')
                self.updateVariable('__status__', self.Status.Idle)
                self.updateVariable('__auxstatus__', '')
                self.error(f'Error in exposure: {remainder}')
#                self.panic()
                self.enableAutoQuery()
        elif (status == 'OK') and (idnum == 7):  # successful end of single exposure
            self.updateVariable('lastcompletedimage', remainder)
            self.updateVariable('__auxstatus__', '')
            if self['__status__'] == self.Status.Stopping:
                # this was a user break, if we are not panicking, we need to re-trim the detector. If panicking,
                # leave the detector as is.
                if self.panicking == self.PanicState.Panicking:
                    # exposure ended, acknowledge the panic
                    super().doPanic()
                else:
                    self.updateVariable('__status__', self.Status.Idle)
                    self.info('Re-trimming the detector after a user break.')
                    self.enqueueHardwareMessage(f'resetcam\r'.encode("ascii"))
                    self.enqueueHardwareMessage(
                        f'SetThreshold {self["gain"]}G {self["threshold"]:.0f}\r'.encode('ascii'))
                    self.messagereplytimeout = 60
                    self.updateVariable('__status__', self.Status.Trimming)
            else:
                # not a user break, just a normal end
                self.updateVariable('__status__', self.Status.Idle)
                self.enableAutoQuery()
        elif status == 'ERR':
            self.error(f'Unknown error reported by the Pilatus detector: {remainder}')
            #self.panic()
        elif (status == 'OK') and (idnum == 2):  # reply to 'camsetup'
            lines = [l.strip() for l in remainder.split('\n')]
            if not ((lines[0] == 'Camera definition:') and
                    (lines[2].startswith('Camera name: ')) and
                    (', S/N' in lines[2]) and
                    (lines[3].startswith('Camera state: ')) and
                    (lines[4].startswith('Target file: ')) and
                    (lines[5].startswith('Time left: ')) and
                    (lines[6].startswith('Last image: ')) and
                    (lines[7].startswith('Master PID is: ')) and
                    (lines[8].startswith('Controlling PID is: ')) and
                    (lines[9].startswith('Exposure time: ')) and
                    (lines[10] == 'Last completed image:') and
                    (lines[12].startswith('Shutter is: '))
            ):
                self.error(f'Bad response from the camsetup command')
            else:
                self.updateVariable('cameradef', lines[1])
                self.updateVariable('cameraname', lines[2].split(':')[1].split(',')[0].strip())
                self.updateVariable('cameraSN', lines[2].split(',')[1].split()[-1])
                self.updateVariable('camstate', lines[3].split(':')[1].strip())
                self.updateVariable('targetfile', lines[4].split(':')[1].strip())
                self.updateVariable('timeleft', float(lines[5].split(':')[1].strip()))
                self.updateVariable('lastimage', lines[6].split(':')[1].strip())
                self.updateVariable('masterPID', int(lines[7].split(':')[1].strip()))
                self.updateVariable('controllingPID', int(lines[8].split(':')[1].strip()))
                self.updateVariable('exptime', float(lines[9].split(':')[1].strip()))
                self.updateVariable('lastcompletedimage', lines[11].strip())
                self.updateVariable('shutterstate', lines[12].split(':')[1].strip())
        elif (status == 'OK') and (idnum == 5):  # df
            self.updateVariable('diskfree', int(remainder))
        elif (status == 'OK') and (idnum == 10):  # image path
            self.updateVariable('imgpath', remainder)
            if self.baseimagepath is None:
                self.baseimagepath = remainder
        elif (status == 'OK') and (idnum == 15) and ((m := re.match(
                    r'Settings: (?P<gain>.+) gain; threshold: (?P<threshold>\d+) eV; '
                    r'vcmp: (?P<vcmp>[+-]?\d+\.\d+) V\n Trim file:\n\s*(?P<trimfile>.+)\s*', remainder)) is not None):
            self.updateVariable('gain', m['gain']+'G')
            self.updateVariable('threshold', float(m['threshold']))
            self.updateVariable('vcmp', float(m['vcmp']))
            self.updateVariable('trimfile', m['trimfile'])
        elif (status == 'OK') and (idnum == 15) and ((m := re.match(r'^N images set to: (?P<nimages>\d+)$', remainder)) is not None):
            self.updateVariable('nimages', int(m['nimages']))
        elif (status == 'OK') and (idnum == 15) and remainder.startswith('chan  Tlo   Thi   Hlo   Hhi'):
            # reply to setlimth: query of temperature and humidity limits
            templimits = []
            humlimits = []
            for line in remainder.split('\n')[1:]:
                channel, tmin, tmax, hmin, hmax = line.strip().split()
                templimits.append((float(tmin), float(tmax)))
                humlimits.append((float(hmin), float(hmax)))
            self.updateVariable('temperaturelimits', tuple(templimits))
            self.updateVariable('humiditylimits', tuple(humlimits))
        elif (status == 'OK') and (idnum == 15) and remainder.startswith('ImgMode is '):
            self.updateVariable('imgmode', remainder.replace('ImgMode is ', ''))
        elif (status == 'OK') and (idnum == 15) and remainder.startswith('Exposure period set to: '):
            self.updateVariable('expperiod', float(remainder.split(':')[1].strip().split()[0]))
        elif (status == 'OK') and (idnum == 15) and remainder.startswith('Exposure time set to: '):
            self.updateVariable('exptime', float(remainder.split(':')[1].strip().split()[0]))
        elif (status == 'OK') and (idnum == 15) and ((m := re.match(
                r'^Rate correction is on; tau = (?P<tau>.*) s, '
                r'cutoff = (?P<cutoff>\d+) counts$', remainder)) is not None):
            self.updateVariable('tau', float(m['tau']))
            self.updateVariable('cutoff', int(m['cutoff']))
        elif (status == 'OK') and (idnum == 15) and (remainder == 'Turn off rate correction'):
            self.updateVariable('tau', 0.0)
            self.updateVariable('cutoff', 1048574)
        elif (status == 'OK') and (idnum == 15) and (remainder == 'Turning off rate correction  Setting gap-fill byte to 0'):
            # e.g. for "imgmode p"
            self.updateVariable('imgmode', 'pulses')
            self.updateVariable('tau', 0.0)
            self.updateVariable('cutoff', 1048574)
        elif (status == 'OK') and (idnum == 15) and ((m := re.match(r'^Rate correction is off, cutoff = (?P<cutoff>\d+) counts$', remainder)) is not None):
            self.updateVariable('tau', 0.0)
            self.updateVariable('cutoff', int(m['cutoff']))
        elif (status == 'OK') and (idnum == 15) and (remainder == '/tmp/setthreshold.cmd'):
            # end of trimming
            self.enableAutoQuery()
            self.updateVariable('__status__', self.Status.Idle)
            self.updateVariable('__auxstatus__', '')
            self.queryVariable('threshold')
            self.queryVariable('tau')
            if self.panicking == self.PanicState.Panicking:
                super().doPanic()
        elif (status == 'OK') and (idnum == 15) and ((m := re.match(r'Starting (?P<exptime>.*) second background: '
                            r'(?P<date>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)$', remainder)) is not None):
            self.updateVariable('exptime', float(m['exptime']))
            self.updateVariable('starttime', dateutil.parser.parse(m['date']))
        elif (status == 'OK') and (idnum == 15) and (not remainder):
            # this can also happen, i.e. just a simple '15 OK'. E.g. by "resetcam" or "imgmode x"
            self.warning(f'15 OK received. Sentmessage: {sentmessage}')
            if sentmessage == b'resetcam\r':
                if self['__status__'] == self.Status.Stopping:
                    # this was a user break, we need to re-trim the detector
                    self.info('Re-trimming the detector after an user break.')
                    self.updateVariable('__status__', self.Status.Idle)
                    self.enqueueHardwareMessage(
                        f'SetThreshold {self["gain"]}G {self["threshold"]:.0f}\r'.encode('ascii'))
                    self.messagereplytimeout = 60
                    self.updateVariable('__status__', self.Status.Trimming)
                else:
                    # other reason of break.
                    self.debug(f'__status__=={self["__status__"]}')
                    self.updateVariable('__status__', self.Status.Idle)
                    self.updateVariable('__auxstatus__', '')
                    self.error(f'Error in exposure: {remainder}')
                    self.enableAutoQuery()
        elif (status == 'OK') and (idnum == 16) and remainder.startswith('PID = '):  # ShowPID
            self.updateVariable('pid', int(remainder.split('=')[1]))
        elif (status == 'OK') and (idnum == 18):
            # telemetry
            lines = [l.strip() for l in remainder.split('\n')]
            if not (lines[0].startswith('=== Telemetry at ')
                    and (lines[0].endswith(' ==='))
                    and (lines[1].startswith('Image format: '))
                    and (lines[1].endswith('(h) pixels'))
                    and (lines[2].startswith('Selected bank: '))
                    and (lines[3].startswith('Selected module: '))
                    and (lines[4].startswith('Selected chip: '))
            ):
                self.error(f'Invalid telemetry message received from the detector: {message}')
            else:
                self.updateVariable(
                    'telemetry_date',
                    dateutil.parser.parse(lines[0].replace('=== Telemetry at ', '').replace(' ===', '')))
                self.updateVariable(
                    'wpix', int(lines[1].split(':')[1].split('(')[0].strip()))
                self.updateVariable(
                    'hpix', int(lines[1].split('x')[1].split('(')[0].strip()))
                self.updateVariable(
                    'sel_bank', int(lines[2].split(':')[1].strip())
                )
                self.updateVariable(
                    'sel_module', int(lines[3].split(':')[1].strip())
                )
                self.updateVariable(
                    'sel_chip', int(lines[4].split(':')[1].strip())
                )
                temp = []
                hum = []
                for line in lines[5:]:
                    try:
                        channel, temperature, humidity = self._interpretTHline(line)
                    except ValueError:
                        self.error(f'Invalid temperature/humidity line: {line}')
                    else:
                        temp.append(temperature)
                        hum.append(humidity)
                self.updateVariable('temperature', tuple(temp))
                self.updateVariable('humidity', tuple(hum))
        elif (status == 'OK') and (idnum == 24) and (remainder.startswith('Code release:')):
            self.updateVariable('version', remainder.split(':', 1)[1].strip())
        elif (status == 'OK') and (idnum == 215):  # THread, i.e. temperature & humidity information
            temp = []
            hum = []
            for line in remainder.split('\n'):
                try:
                    channel, temperature, humidity = self._interpretTHline(line.strip())
                except ValueError:
                    self.error(f'Invalid temperature/humidity line: {line}')
                else:
                    temp.append(temperature)
                    hum.append(humidity)
            self.updateVariable('temperature', tuple(temp))
            self.updateVariable('humidity', tuple(hum))
        else:
            self.error(f'Invalid message received from detector: {message}. Last sent message: {sentmessage}')


    def issueCommand(self, name: str, args: Sequence[Any]):
        if name == 'trim':
            threshold, gain = args
            if self.connectionIsReadOnly():
                self.commandError(name, 'Read-only connection')
            self.disableAutoQuery()
            self.enqueueHardwareMessage(f'SetThreshold {gain} {threshold:f}\r'.encode("ascii"))
            self.messagereplytimeout = 60
            self.updateVariable('__status__', self.Status.Trimming)
            self.commandFinished(name, 'Started trimming')
        elif name == 'expose':
            relimgpath, firstfilename, exptime, nimages, delay = args
            #self.debug(f'Starting exposure {relimgpath=}, {firstfilename=}, {exptime=}, {nimages=}, {delay=}')
            if exptime < 1e-7 or exptime > 1e6:
                self.commandError(name, 'Invalid value for exposure time')
                return
            if nimages < 1:
                self.commandError(name, 'Invalid number of images')
                return
            if delay < self.minimal_exposure_delay:
                self.commandError(name, 'Too short exposure delay')
                return
            if self.connectionIsReadOnly():
                self.commandError(name, 'Read-only connection')
            self.disableAutoQuery()
            self.enqueueHardwareMessage(f'imgpath {self.baseimagepath}/{relimgpath}\r'.encode('ascii'))
            self.enqueueHardwareMessage(f'expperiod {exptime + delay:f}\r'.encode('ascii'))
            self.enqueueHardwareMessage(f'nimages {nimages}\r'.encode('ascii'))
            self.enqueueHardwareMessage(f'exptime {exptime}\r'.encode('ascii'))
            fulltime = nimages * exptime + (nimages - 1) * delay
            self.enqueueHardwareMessage(f'Exposure {firstfilename}\r'.encode('ascii'), numreplies=2)
            self.updateVariable('__status__', self.Status.Exposing if nimages == 1 else self.Status.ExposingMulti)
            self.commandFinished(name, 'Started exposure')
        elif name == 'stopexposure':
            self.stopExposure()
        else:
            self.commandError(name, f'Unknown command: {name}')

    def stopExposure(self):
        """Do what it takes to stop an ongoing exposure"""
        if self['__status__'] == self.Status.Exposing:
            # single exposure, do a "resetcam", then trim again.
            # A dirty trick is involved here. By default, the communicator process refuses to send a message until
            # a reply is received. Thus until the reply for "Exposure" is received, we cannot send the "resetcam"
            # command to stop the exposure. We will therefore assume that we got a reply to "Exposure" which will
            # make us able to send another message.

            # but first we ascertain if the last command was really the Exposure command.
            assert self.lastmessage[0].startswith(b'Exposure ')
            # no messages should be pending.
            if self.connectionIsReadOnly():
                self.commandError(name, 'Read-only connection')

            #                assert self.outbuffer.qsize() == 0
            while self.outbuffer.qsize() > 0:
                self.warning(f'Outbuffer not empty! Queue size is: {self.outbuffer.qsize()}')
            self.enqueueHardwareMessage(b'resetcam\r')
            self.lastmessage = None
            self.cleartosend.set()
            self.updateVariable('__status__', self.Status.Stopping)
            self.commandFinished(name, 'Stopping a single exposure')
        elif self['__status__'] == self.Status.ExposingMulti:
            # we do the same trick as above, only we have to issue the "K" command.
            assert self.lastmessage[0].startswith(b'Exposure ')
            if self.connectionIsReadOnly():
                self.commandError(name, 'Read-only connection')
            # assert self.outbuffer.qsize() == 0
            # the command "K" by itself does not elicit a reply, but the multiple exposure does. Since we clear all
            # traces of the last 'Exposure' command by resetting `self.lastmessage`, the reply from the detector
            # will be attibuted by us to the "K" command, hence "numreplies=1".
            while self.outbuffer.qsize() > 0:
                self.warning(f'Outbuffer not empty! Queue size is: {self.outbuffer.qsize()}')
            self.enqueueHardwareMessage(b'K\r', numreplies=2)
            self.lastmessage = None
            self.cleartosend.set()
            self.updateVariable('__status__', self.Status.Stopping)
            self.commandFinished(name, 'Stopping a multiple exposure sequence')
        elif self['__status__'] == self.Status.Stopping:
            self.commandError(name, 'Already stopping...')
        else:
            self.commandError(name, 'No ongoing exposure')

    def connectionIsReadOnly(self) -> bool:
        try:
            return self['pid'] != self['controllingPID']
        except ValueError:
            return True

    def doPanic(self):
        self.panicking = self.PanicState.Panicking
        if self['__status__'] in [self.Status.Exposing, self.Status.ExposingMulti]:
            self.stopExposure()
        elif self['__status__'] in [self.Status.Trimming]:
            pass  # do nothing, when the trimming is done, panic will be acknowledged
        elif self['__status__'] in [self.Status.Stopping]:
            pass # do nothing, when the system is settled, panic will be acknowledged
        elif self['__status__'] == self.Status.Idle:
            super().doPanic()
        else:
            self.error(f'Panicking in state {self["__status__"]}')
            super().doPanic()

