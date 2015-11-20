import datetime
import logging
import multiprocessing
import queue

from .device import Device_TCP

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HaakePhoenix(Device_TCP):
    allvariables = ['firmwareversion', 'faultstatus', 'fuzzycontrol', 'fuzzystatus', 'temperature_internal',
                    'temperature_external', 'setpoint', 'highlimit', 'lowlimit', 'diffcontrol_on', 'autostart',
                    'fuzzyid', 'beep', 'time', 'date', 'watchdog_on',
                    'watchdog_setpoint', 'cooling_on', 'pump_power']

    urgentvariables = ['faultstatus', 'time', 'temperature_internal', 'temperature_external']

    notsourgentvariables = ['cooling_on', 'pump_power', 'setpoint', 'date', 'date']

    backend_interval = 0.1

    def __init__(self, *args, **kwargs):
        Device_TCP.__init__(self, *args, **kwargs)
        # communication between software and hardware must be synchronous:
        # we cannot send until we got a reply. This queue stores the messages
        # until they become available to send.
        self._sendqueue = multiprocessing.Queue()
        self._urgency_counter = 0
        self._stashmessage = b''

    def _execute_command(self, commandname, arguments):
        if commandname == 'start':
            self._send(b'W TS 1\r')
        elif commandname == 'stop':
            self._send(b'W TS 0\r')
        elif commandname == 'alarm':
            self._send(b'W AL\r')
        elif commandname == 'alarm_confirm':
            self._send(b'W EG\r')
        else:
            raise NotImplementedError(commandname)

    def _has_all_variables(self):
        missing = [x for x in self.allvariables if x not in self._properties]
        #        if missing:
        #            self._logger.debug('HaakePhoenix missing variables: %s'%', '.join(missing))
        return not missing

    def _process_incoming_message(self, message):
        #        print('RECEIVED: '+message.decode('ascii')+'\n')
        #        print('LASTSENT: '+self._lastsent[:-1].decode('ascii'))
        message = self._stashmessage + message
        try:
            if not hasattr(self, '_lastsent'):
                self._logger.debug('No lastsent for message: %s' % message.decode('utf-8').replace('\r', ''))
                # print('!!! NOLASTSENT')
                return
            if message == b'F001\r':
                # unknown command
                lastcommand = self._lastsent.decode('ascii').replace('\r', '')
                self._logger.debug(
                    'Unknown command reported by circulator. Lastcommand: *%s*' % lastcommand)
                return
            if message == b'F123\r':
                self._logger.warning('Error 123 reported by circulator.')
                return
            elif message == b'FE00\r':
                # might be a bug in the firmware
                message = b'FE00$\r'
            if not message.endswith(b'$\r'):
                self._logger.warning('Malformed message: does not end with "$\\r": %s' % message)
                self._stashmessage = self._stashmessage + message
                return
            self._stashmessage = b''
            message = message[:-1]
            if self._lastsent == b'R V1\r':
                self._update_variable('firmwareversion', message[:-1].decode('utf-8'))
            elif message.startswith(b'BS'):
                flags = int(message[2:-1], base=2)
                self._update_variable('external_pt100_error', bool(flags & 0b1))
                self._update_variable('internal_pt100_error', bool(flags & 0b10))
                self._update_variable('liquid_level_low_error', bool(flags & 0b100))
                # bit #4 is reserved
                self._update_variable('cooling_error', bool(flags & 0b10000))
                self._update_variable('external_alarm_error', bool(flags & 0b100000))
                self._update_variable('pump_overload_error', bool(flags & 0b1000000))
                self._update_variable('liquid_level_alarm_error', bool(flags & 0b10000000))
                self._update_variable('overtemperature_error', bool(flags & 0b100000000))
                self._update_variable('main_relay_missing_error', bool(flags & 0b1000000000))
                self._update_variable('control_external', bool(flags & 0b10000000000))
                self._update_variable('control_on', bool(flags & 0b100000000000))
                self._update_variable('faultstatus', flags)
            elif message.startswith(b'FB'):
                self._update_variable('fuzzycontrol', message[2:-1].decode('utf-8'))
            elif message.startswith(b'FE'):
                self._update_variable('fuzzystatus', int(message[2:-1]))
            elif message.startswith(b'T1'):
                self._update_variable('temperature_internal', float(message[2:-1]))
            elif message.startswith(b'T3'):
                self._update_variable('temperature_external', float(message[2:-1]))
            elif message.startswith(b'SW'):
                self._update_variable('setpoint', float(message[2:-1]))
            elif message.startswith(b'HL'):
                self._update_variable('highlimit', float(message[2:-1]))
            elif message.startswith(b'LL'):
                self._update_variable('lowlimit', float(message[2:-1]))
            elif self._lastsent == b'IN MODE 5\r':
                if len(message) == 2:
                    self._update_variable('control_on', bool(int(message[0:1])))
                else:
                    self._logger.debug('Invalid message for control_on: %s' % message.decode('utf-8'))
                    raise NotImplementedError((self._lastsent, message))
            elif self._lastsent == b'IN MODE 2\r':
                if len(message) == 2:
                    self._update_variable('control_external', bool(int(message[0:1])))
                else:
                    self._logger.debug('Invalid message for control_external: %s' % message.decode('utf-8'))
                    raise NotImplementedError((self._lastsent, message))
            elif message.startswith(b'FR'):
                self._update_variable('diffcontrol_on', bool(int(message[2:3])))
            elif message.startswith(b'ZA'):
                self._update_variable('autostart', bool(int(message[2:3])))
            elif message.startswith(b'ZI'):
                self._update_variable('fuzzyid', bool(int(message[2:3])))
            elif message.startswith(b'ZB'):
                self._update_variable('beep', bool(int(message[2:3])))
            elif message.startswith(b'XT'):
                hour, min, sec = [int(x) for x in message[2:-1].split(b':')]
                try:
                    self._update_variable('time', datetime.time(hour, min, sec))
                except ValueError:
                    # the real-time clock on some units can sometime glitch
                    self._update_variable('time', datetime.time(0, 0, 0))
            elif message.startswith(b'XD'):
                day, month, year = [int(x) for x in message[2:-1].split(b'.')]
                try:
                    self._update_variable('date', datetime.date(year + 2000, month, day))
                except ValueError:
                    # the real-time clock on some units can sometime glitch
                    self._update_variable('date', datetime.date(1900, 1, 1))
            elif message.startswith(b'WD'):
                self._update_variable('watchdog_on', bool(int(message[2:3])))
            elif message.startswith(b'WS'):
                self._update_variable('watchdog_setpoint', float(message[2:-1]))
            elif message.startswith(b'CC'):
                self._update_variable('cooling_on', bool(int(message[2:3])))
            elif message.startswith(b'PF'):
                if self._update_variable('pump_power', float(message[2:-1])):
                    if float(message[2:-1]) > 0:
                        self._update_variable('_status', 'running')
                    else:
                        self._update_variable('_status', 'stopped')
            elif message == b'$':
                # confirmation for the last command
                self._logger.debug(
                    'Confirmation for message %s received.' % self._lastsent.decode('utf-8').replace('\r', ''))
            else:
                self._logger.debug('Unknown message: %s' % message.decode('utf-8').replace('\r', ''))
        finally:
            try:
                if self._stashmessage:
                    # we are waiting for the end of the message
                    return
                msg = self._sendqueue.get_nowait()
                self._lastsent = msg
                Device_TCP._send(self, msg)
            except queue.Empty:
                try:
                    del self._lastsent
                except AttributeError:
                    pass

    def _query_variable(self, variablename):
        if variablename is None:
            if self._sendqueue.qsize() > 3:
                # skip autoupdate
                return
            toberefreshed = [x for x in self.allvariables if x not in self._properties] + self.urgentvariables
            if not self._urgency_counter:
                toberefreshed.extend(self.notsourgentvariables)
            for vn in set(toberefreshed):
                self.refresh_variable(vn, signal_needed=False)
            self._urgency_counter = (self._urgency_counter + 1) % 10
            return
        if variablename == 'firmwareversion':
            self._send(b'R V1\r')
        elif variablename in ['faultstatus', 'external_pt100_error', 'internal_pt100_error', 'liquid_level_low_error',
                              'cooling_error',
                              'external_alarm_error', 'pump_overload_error', 'liquid_level_alarm_error',
                              'overtemperature_error',
                              'main_relay_missing_error', 'status_control_external', 'status_temperature_control']:
            self._send(b'R BS\r')
        elif variablename == 'fuzzycontrol':
            self._send(b'R FB\r')
        elif variablename == 'fuzzystatus':
            self._send(b'R FE\r')
        elif variablename == 'temperature_internal':
            self._send(b'R T1\r')
        elif variablename == 'temperature_external':
            self._send(b'R T3\r')
        elif variablename == 'setpoint':
            self._send(b'R SW\r')
        elif variablename == 'highlimit':
            self._send(b'R HL\r')
        elif variablename == 'lowlimit':
            self._send(b'R LL\r')
        elif variablename == 'control_on':
            self._send(b'IN MODE 5\r')
        elif variablename == 'control_external':
            self._send(b'IN MODE 2\r')
        elif variablename == 'diffcontrol_on':
            self._send(b'R FR\r')
        elif variablename == 'autostart':
            self._send(b'R ZA\r')
        elif variablename == 'fuzzyid':
            self._send(b'R ZI\r')
        elif variablename == 'beep':
            self._send(b'R ZB\r')
        elif variablename == 'time':
            self._send(b'R XT\r')
        elif variablename == 'date':
            self._send(b'R XD\r')
        elif variablename == 'watchdog_on':
            self._send(b'R WD\r')
        elif variablename == 'watchdog_setpoint':
            self._send(b'R WS\r')
        elif variablename == 'cooling_on':
            self._send(b'R CC\r')
        elif variablename == 'pump_power':
            self._send(b'R PF\r')
        else:
            raise NotImplementedError(variablename)
        pass

    def _set_variable(self, variable, value):
        self._logger.debug('Setting circulator variable from process %s' % multiprocessing.current_process().name)
        if variable == 'setpoint':
            self._logger.debug('Setting setpoint. Sending: W SW %.2f<cr>' % value)
            self._send(b'W SW %.2f\r' % value)
        elif variable == 'highlimit':
            self._send(b'W HL %.2f\r' % value)
        elif variable == 'lowlimit':
            self._send(b'W LL %.2f\r' % value)
        elif variable == 'highlimit':
            self._send(b'W HL %.2f\r' % value)
        elif variable == 'control_external':
            self._send(b'OUT MODE 2 %d\r' % bool(value))
        elif variable == 'diffcontrol_on':
            self._send(b'W FR %d\r' % bool(value))
        elif variable == 'autostart':
            self._send(b'W ZA %d\r' % bool(value))
        elif variable == 'fuzzyid':
            self._send(b'W ZI %d\r' % bool(value))
        elif variable == 'beep':
            self._send(b'W ZB %d\r' % bool(value))
        elif variable == 'date':
            assert (isinstance(value, datetime.date))
            self._send(b'W XD %02d.%02d.%02d\r' % (value.day, value.month, value.year % 100))
        elif variable == 'time':
            assert (isinstance(value, datetime.time))
            self._send(b'W XT %02d:%02d:%02d\r' % (value.hour, value.minute, value.second))
        elif variable == 'watchdog_on':
            self._send(b'W WD %d\r' % bool(value))
        elif variable == 'watchdog_setpoint':
            self._send(b'W WS %6.2f\r' % value)
        elif variable == 'cooling_on':
            self._send(b'W CC %d\r' % bool(value))
        elif variable == 'pump_power':
            assert (value >= 5)
            assert (value <= 100)
            self._send(b'W PF %5.2f\r' % value)
        else:
            raise NotImplementedError(variable)

        self.refresh_variable(variable, signal_needed=False)
        pass

    def _send(self, message):
        if hasattr(self, '_lastsent'):
            self._sendqueue.put_nowait(message)
            return
        self._lastsent = message
        Device_TCP._send(self, message)

    def decode_error_flags(self, flags):
        lis = []
        return lis
