import datetime
import logging
import multiprocessing

from .device import Device_TCP, ReadOnlyVariable, InvalidValue, UnknownCommand, UnknownVariable, CommunicationError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HaakePhoenix(Device_TCP):
    log_formatstr = '{setpoint}\t{temperature_internal}\t{faultstatus}\t{pump_power}\t{cooling_on}'

    _all_variables = ['firmwareversion', 'faultstatus', 'fuzzycontrol', 'fuzzystatus', 'temperature_internal',
                    'temperature_external', 'setpoint', 'highlimit', 'lowlimit', 'diffcontrol_on', 'autostart',
                    'fuzzyid', 'beep', 'time', 'date', 'watchdog_on',
                    'watchdog_setpoint', 'cooling_on', 'pump_power', 'external_pt100_error', 'internal_pt100_error',
                      'liquid_level_low_error',
                      'cooling_error',
                      'external_alarm_error', 'pump_overload_error', 'liquid_level_alarm_error',
                      'overtemperature_error',
                      'main_relay_missing_error', 'status_control_external', 'status_temperature_control'
                      ]

    _urgentvariables = ['faultstatus', 'time', 'temperature_internal', 'temperature_external', 'pump_power']

    _notsourgentvariables = ['cooling_on', 'setpoint','date']

    _minimum_query_variables = ['faultstatus', 'time', 'temperature_internal', 'temperature_external', 'pump_power',
                                'cooling_on', 'setpoint', 'date', 'firmwareversion', 'fuzzycontrol','fuzzystatus',
                                'highlimit', 'lowlimit', 'diffcontrol_on', 'autostart', 'fuzzyid', 'beep',
                                'watchdog_on', 'watchdog_setpoint']
    backend_interval = 0.1

    def __init__(self, *args, **kwargs):
        Device_TCP.__init__(self, *args, **kwargs)
        # This counter is incremented at each query-all event (call of
        # `self._query_variable(None)` and the modulus by 10 is taken.
        # Refresh of the variables in `self.notsourgentvariables` is initiated
        # only if the value of this counter is zero.
        self._urgency_counter = 0

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
            raise UnknownCommand(commandname)

    def _get_complete_messages(self, message):
        if len(message)>64:
            raise CommunicationError('Haake Phoenix circulator not connected or not turned on, receiving garbage messages.')
        messages=message.split(b'\r')
        for i in range(len(messages)-1):
            messages[i]=messages[i]+b'\r'
        return messages

    def _process_incoming_message(self, message, original_sent=None):
        # The Haake Phoenix circulator always gives at most 1 reply for each
        # sent message, therefore we are safe to release the cleartosend
        # semaphore at this point, so while we are handling this message,
        # the sending process can commence sending the next message.
        self._cleartosend_semaphore.release()

        if message == b'F001\r':
            # unknown command
            lastcommand = original_sent.decode('ascii').replace('\r', '')
            self._logger.debug(
                'Unknown command reported by circulator. Lastcommand: *%s*' % lastcommand)
            return
        if message == b'F123\r':
            self._logger.warning('Error 123 reported by circulator.')
            return
        elif message == b'FE00\r':
            # might be a bug in the firmware
            message = b'FE00$\r'
        # At this point, all messages should end with b"$\r"
        assert(message.endswith(b'$\r'))
        message = message[:-2]
        if original_sent == b'R V1\r':
            self._update_variable('firmwareversion', message.decode('utf-8'))
        elif message.startswith(b'BS'):
            flags = int(message[2:], base=2)
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
            self._update_variable('fuzzycontrol', message[2:].decode('utf-8'))
        elif message.startswith(b'FE'):
            self._update_variable('fuzzystatus', int(message[2:]))
        elif message.startswith(b'T1'):
            if self._update_variable('temperature_internal', float(message[2:])):
                self._update_variable('_auxstatus','%.2f°C'%float(message[2:]))
        elif message.startswith(b'T3'):
            self._update_variable('temperature_external', float(message[2:]))
        elif message.startswith(b'SW'):
            self._update_variable('setpoint', float(message[2:]))
        elif message.startswith(b'HL'):
            self._update_variable('highlimit', float(message[2:]))
        elif message.startswith(b'LL'):
            self._update_variable('lowlimit', float(message[2:]))
        elif original_sent == b'IN MODE 5\r':
            if len(message) == 1:
                self._update_variable('control_on', bool(int(message)))
            else:
                self._logger.debug('Invalid message for control_on: %s' % message.decode('utf-8'))
                raise NotImplementedError((original_sent, message))
        elif original_sent == b'IN MODE 2\r':
            if len(message) == 1:
                self._update_variable('control_external', bool(int(message)))
            else:
                self._logger.debug('Invalid message for control_external: %s' % message.decode('utf-8'))
                raise NotImplementedError((original_sent, message))
        elif message.startswith(b'FR'):
            self._update_variable('diffcontrol_on', bool(int(message[2:3])))
        elif message.startswith(b'ZA'):
            self._update_variable('autostart', bool(int(message[2:3])))
        elif message.startswith(b'ZI'):
            self._update_variable('fuzzyid', bool(int(message[2:3])))
        elif message.startswith(b'ZB'):
            self._update_variable('beep', bool(int(message[2:3])))
        elif message.startswith(b'XT'):
            hour, min, sec = [int(x) for x in message[2:].split(b':')]
            try:
                self._update_variable('time', datetime.time(hour, min, sec))
            except ValueError:
                # the real-time clock on some units can sometime glitch
                self._update_variable('time', datetime.time(0, 0, 0))
        elif message.startswith(b'XD'):
            day, month, year = [int(x) for x in message[2:].split(b'.')]
            try:
                self._update_variable('date', datetime.date(year + 2000, month, day))
            except ValueError:
                # the real-time clock on some units can sometime glitch
                self._update_variable('date', datetime.date(1900, 1, 1))
        elif message.startswith(b'WD'):
            self._update_variable('watchdog_on', bool(int(message[2:3])))
        elif message.startswith(b'WS'):
            self._update_variable('watchdog_setpoint', float(message[2:]))
        elif message.startswith(b'CC'):
            self._update_variable('cooling_on', bool(int(message[2:3])))
        elif message.startswith(b'PF'):
            if self._update_variable('pump_power', float(message[2:])):
                if float(message[2:]) > 0:
                    self._update_variable('_status', 'running')
                else:
                    self._update_variable('_status', 'stopped')
        elif message == b'':
            # confirmation for the last command
            self._logger.debug(
                'Confirmation for message %s received.' % original_sent.decode('utf-8').replace('\r', ''))
        else:
            raise CommunicationError('Unknown message: %s' % message.decode('utf-8').replace('\r', ''))

    def _query_variable(self, variablename, minimum_query_variables=None):
        if variablename is None:
            toberefreshed = [x for x in self._minimum_query_variables if x not in self._properties] + self._urgentvariables
            if not self._urgency_counter:
                toberefreshed.extend(self._notsourgentvariables)
            super()._query_variable(None, minimum_query_variables=toberefreshed)
            self._urgency_counter = (self._urgency_counter + 1) % 10
            return False
        if not super()._query_variable(variablename):
            return False
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
            raise UnknownVariable(variablename)

    def _set_variable(self, variable, value):
        self._logger.debug('Setting circulator variable from process %s' % multiprocessing.current_process().name)
        try:
            if variable == 'setpoint':
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
            elif variable in self.allvariables:
                raise ReadOnlyVariable(variable)
            else:
                raise UnknownVariable(variable)
        except AssertionError as ae:
            raise InvalidValue(value)
        self.refresh_variable(variable, signal_needed=False)

    def decode_error_flags(self, flags):
        return []
