import datetime
import logging
import multiprocessing
from typing import Tuple, List

from .device import DeviceBackend_TCP, ReadOnlyVariable, InvalidValue, UnknownCommand, UnknownVariable, \
    CommunicationError, Device, InvalidMessage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# noinspection PyPep8Naming
class HaakePhoenix_Backend(DeviceBackend_TCP):
    reply_timeout = 10

    def execute_command(self, commandname: str, arguments: Tuple):
        if commandname == 'start':
            self.send_message(b'W TS 1\r')
        elif commandname == 'stop':
            self.send_message(b'W TS 0\r')
        elif commandname == 'alarm':
            self.send_message(b'W AL\r')
        elif commandname == 'alarm_confirm':
            self.send_message(b'W EG\r')
        else:
            raise UnknownCommand(commandname)

    @staticmethod
    def get_complete_messages(message: bytes) -> List[bytes]:
        if len(message) > 64:
            raise CommunicationError(
                'Haake Phoenix circulator not connected or not turned on, receiving garbage messages.')
        messages = message.split(b'\r')
        for i in range(len(messages) - 1):
            messages[i] = messages[i] + b'\r'
        return messages

    def process_incoming_message(self, message: bytes, original_sent=None):
        if message == b'F001\r':
            # unknown command
            lastcommand = original_sent.decode('ascii').replace('\r', '')
            self.logger.debug(
                'Unknown command reported by circulator. Lastcommand: *{}*'.format(lastcommand))
            self.logger.debug('Outqueue size: {:d}'.format(self.outqueue.qsize()))
            self.send_message(original_sent)
            raise InvalidMessage(message)
        if message == b'F123\r':
            self.logger.warning('Error 123 reported by circulator.')
            raise InvalidMessage(message)
        elif message == b'FE00\r':
            # might be a bug in the firmware, this message must end with a $\r
            message = b'FE00$\r'
        # At this point, all messages should end with b"$\r"
        if not message.endswith(b'$\r'):
            self.logger.warning('Message does not end with "$\\r": {}'.format(message))
            raise InvalidMessage(message)
        message = message[:-2]
        if original_sent == b'R V1\r':
            self.update_variable('firmwareversion', message.decode('utf-8'))
        elif message.startswith(b'BS'):
            flags = int(message[2:], base=2)
            self.update_variable('external_pt100_error', bool(flags & 0b1))
            self.update_variable('internal_pt100_error', bool(flags & 0b10))
            self.update_variable('liquid_level_low_error', bool(flags & 0b100))
            # bit #4 is reserved
            self.update_variable('cooling_error', bool(flags & 0b10000))
            self.update_variable('external_alarm_error', bool(flags & 0b100000))
            self.update_variable('pump_overload_error', bool(flags & 0b1000000))
            self.update_variable('liquid_level_alarm_error', bool(flags & 0b10000000))
            self.update_variable('overtemperature_error', bool(flags & 0b100000000))
            self.update_variable('main_relay_missing_error', bool(flags & 0b1000000000))
            self.update_variable('control_external', bool(flags & 0b10000000000))
            self.update_variable('control_on', bool(flags & 0b100000000000))
            self.update_variable('faultstatus', flags)
        elif message.startswith(b'FB'):
            self.update_variable('fuzzycontrol', message[2:].decode('utf-8'))
        elif message.startswith(b'FE'):
            self.update_variable('fuzzystatus', int(message[2:]))
        elif message.startswith(b'T1'):
            if self.update_variable('temperature_internal', float(message[2:])):
                self.update_variable('_auxstatus', '{:.2f}°C'.format(float(message[2:])))
            try:
                if not self.properties['control_external']:
                    self.update_variable('temperature', float(message[2:]))
            except KeyError:
                pass
        elif message.startswith(b'T3'):
            self.update_variable('temperature_external', float(message[2:]))
            try:
                if self.properties['control_external']:
                    self.update_variable('temperature', float(message[2:]))
            except KeyError:
                pass
        elif message.startswith(b'SW'):
            self.update_variable('setpoint', float(message[2:]))
        elif message.startswith(b'HL'):
            self.update_variable('highlimit', float(message[2:]))
        elif message.startswith(b'LL'):
            self.update_variable('lowlimit', float(message[2:]))
        elif original_sent == b'IN MODE 5\r':
            if len(message) == 1:
                self.update_variable('control_on', bool(int(message)))
            else:
                self.logger.debug('Invalid message for control_on: ' + message.decode('utf-8'))
                raise InvalidMessage(message)
        elif original_sent == b'IN MODE 2\r':
            if len(message) == 1:
                if self.update_variable('control_external', bool(int(message))):
                    try:
                        if int(message):
                            self.update_variable('temperature',
                                                 self.properties[
                                                     'temperature_external'])
                        else:
                            self.update_variable('temperature',
                                                 self.properties[
                                                     'temperature_internal'])
                    except KeyError:
                        pass
            else:
                self.logger.debug('Invalid message for control_external: ' + message.decode('utf-8'))
                raise InvalidMessage(message)
        elif message.startswith(b'FR'):
            self.update_variable('diffcontrol_on', bool(int(message[2:3])))
        elif message.startswith(b'ZA'):
            self.update_variable('autostart', bool(int(message[2:3])))
        elif message.startswith(b'ZI'):
            self.update_variable('fuzzyid', bool(int(message[2:3])))
        elif message.startswith(b'ZB'):
            self.update_variable('beep', bool(int(message[2:3])))
        elif message.startswith(b'XT'):
            hour, minute, sec = [int(x) for x in message[2:].split(b':')]
            try:
                self.update_variable('time', datetime.time(hour, minute, sec))
            except ValueError:
                # the real-time clock on some units can sometime glitch
                self.update_variable('time', datetime.time(0, 0, 0))
        elif message.startswith(b'XD'):
            day, month, year = [int(x) for x in message[2:].split(b'.')]
            try:
                self.update_variable('date', datetime.date(year + 2000, month, day))
            except ValueError:
                # the real-time clock on some units can sometime glitch
                self.update_variable('date', datetime.date(1900, 1, 1))
        elif message.startswith(b'WD'):
            self.update_variable('watchdog_on', bool(int(message[2:3])))
        elif message.startswith(b'WS'):
            self.update_variable('watchdog_setpoint', float(message[2:]))
        elif message.startswith(b'CC'):
            self.update_variable('cooling_on', bool(int(message[2:3])))
        elif message.startswith(b'PF'):
            if self.update_variable('pump_power', float(message[2:])):
                if float(message[2:]) > 0:
                    self.update_variable('_status', 'running')
                else:
                    self.update_variable('_status', 'stopped')
        elif message == b'':
            # confirmation for the last command
            if original_sent == b'W TS 1\r':
                self.update_variable('_status', 'running', force=True)
            elif original_sent == b'W TS 0\r':
                self.update_variable('_status', 'stopped', force=True)
            self.logger.debug(
                'Confirmation for message {} received.'.format(original_sent.decode('utf-8').replace('\r', '')))
        else:
            self.logger.debug('Unknown message: ' + message.decode('utf-8').replace('\r', ''))
            self.send_message(original_sent)
            raise InvalidMessage(message)

    def query_variable(self, variablename, minimum_query_variables=None):
        if variablename == 'firmwareversion':
            self.send_message(b'R V1\r', expected_replies=1, asynchronous=False)
        elif variablename in ['faultstatus', 'external_pt100_error', 'internal_pt100_error', 'liquid_level_low_error',
                              'cooling_error',
                              'external_alarm_error', 'pump_overload_error', 'liquid_level_alarm_error',
                              'overtemperature_error',
                              'main_relay_missing_error', 'status_control_external', 'status_temperature_control']:
            self.send_message(b'R BS\r', expected_replies=1, asynchronous=False)
        elif variablename == 'fuzzycontrol':
            if 'firmwareversion' not in self.properties:
                return False
            elif self.properties['firmwareversion'].startswith('2P/H'):
                self.send_message(b'R FB\r', expected_replies=1, asynchronous=False)
            else:
                self.update_variable('fuzzycontrol', 'not supported')
        elif variablename == 'fuzzystatus':
            if 'firmwareversion' not in self.properties:
                return False
            elif self.properties['firmwareversion'].startswith('2P/'):
                self.send_message(b'R FE\r', expected_replies=1, asynchronous=False)
            else:
                self.update_variable('fuzzystatus', False)
        elif variablename == 'temperature_internal':
            self.send_message(b'R T1\r', expected_replies=1, asynchronous=False)
        elif variablename == 'temperature_external':
            self.send_message(b'R T3\r', expected_replies=1, asynchronous=False)
        elif variablename == 'temperature':
            if 'control_external' not in self.properties:
                return False
            elif self.properties['control_external']:
                self.send_message(b'R T3\r', expected_replies=1, asynchronous=False)
            else:
                self.send_message(b'R T1\r', expected_replies=1, asynchronous=False)
        elif variablename == 'setpoint':
            self.send_message(b'R SW\r', expected_replies=1, asynchronous=False)
        elif variablename == 'highlimit':
            self.send_message(b'R HL\r', expected_replies=1, asynchronous=False)
        elif variablename == 'lowlimit':
            self.send_message(b'R LL\r', expected_replies=1, asynchronous=False)
        elif variablename == 'control_on':
            self.send_message(b'IN MODE 5\r', expected_replies=1, asynchronous=False)
        elif variablename == 'control_external':
            self.send_message(b'IN MODE 2\r', expected_replies=1, asynchronous=False)
        elif variablename == 'diffcontrol_on':
            self.send_message(b'R FR\r', expected_replies=1, asynchronous=False)
        elif variablename == 'autostart':
            self.send_message(b'R ZA\r', expected_replies=1, asynchronous=False)
        elif variablename == 'fuzzyid':
            self.send_message(b'R ZI\r', expected_replies=1, asynchronous=False)
        elif variablename == 'beep':
            self.send_message(b'R ZB\r', expected_replies=1, asynchronous=False)
        elif variablename == 'time':
            self.send_message(b'R XT\r', expected_replies=1, asynchronous=False)
        elif variablename == 'date':
            self.send_message(b'R XD\r', expected_replies=1, asynchronous=False)
        elif variablename == 'watchdog_on':
            self.send_message(b'R WD\r', expected_replies=1, asynchronous=False)
        elif variablename == 'watchdog_setpoint':
            self.send_message(b'R WS\r', expected_replies=1, asynchronous=False)
        elif variablename == 'cooling_on':
            self.send_message(b'R CC\r', expected_replies=1, asynchronous=False)
        elif variablename == 'pump_power':
            self.send_message(b'R PF\r', expected_replies=1, asynchronous=False)
        else:
            raise UnknownVariable(variablename)
        return True

    def set_variable(self, variable, value):
        self.logger.debug('Setting circulator variable from process ' + multiprocessing.current_process().name)
        if variable == 'setpoint':
            self.logger.debug('Setting setpoint to {:f}'.format(value))
            self.send_message('W SW {:.2f}\r'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
            self.logger.debug('Setpoint setting message queued.')
        elif variable == 'highlimit':
            self.send_message('W HL {:.2f}\r'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'lowlimit':
            self.send_message('W LL {:.2f}\r'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'highlimit':
            self.send_message('W HL {:.2f}\r'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'control_external':
            self.send_message('OUT MODE 2 {:d}\r'.format(bool(value)).encode('ascii'), expected_replies=1,
                              asynchronous=False)
        elif variable == 'diffcontrol_on':
            self.send_message('W FR {:d}\r'.format(bool(value)).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'autostart':
            self.send_message('W ZA {:d}\r'.format(bool(value)).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'fuzzyid':
            self.send_message('W ZI {:d}\r'.format(bool(value)).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'beep':
            self.send_message('W ZB {:d}\r'.format(bool(value)).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'date':
            assert isinstance(value, datetime.date)
            self.send_message(
                'W XD {0.day:02d}.{0.month:02d}.{1:02d}\r'.format(value, int(value.year) % 100).encode('ascii'),
                expected_replies=1, asynchronous=False)
        elif variable == 'time':
            assert isinstance(value, datetime.time)
            self.send_message('W XT {0.hour:02d}:{0.minute:02d}:{0.second:02d}\r'.format(value).encode('ascii'),
                              expected_replies=1, asynchronous=False)
        elif variable == 'watchdog_on':
            self.send_message('W WD {:d}\r'.format(bool(value)).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'watchdog_setpoint':
            self.send_message('W WS {:6.2}f\r'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'cooling_on':
            self.send_message('W CC {:d}\r'.format(bool(value)).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable == 'pump_power':
            if (value < 5) or (value > 100):
                raise InvalidValue(value)
            self.send_message('W PF {:5.2f}\r'.format(value).encode('ascii'), expected_replies=1, asynchronous=False)
        elif variable in self.all_variables:
            raise ReadOnlyVariable(variable)
        else:
            raise UnknownVariable(variable)


class HaakePhoenix(Device):
    log_formatstr = '{setpoint:.2f}\t{temperature_internal:.2f}\t{faultstatus}\t{pump_power}\t{cooling_on}'

    all_variables = ['firmwareversion', 'faultstatus', 'fuzzycontrol',
                     'fuzzystatus', 'temperature_internal',
                     'temperature_external', 'setpoint', 'highlimit',
                     'lowlimit', 'diffcontrol_on', 'autostart', 'fuzzyid',
                     'beep', 'time', 'date', 'watchdog_on',
                     'watchdog_setpoint', 'cooling_on', 'pump_power',
                     'external_pt100_error', 'internal_pt100_error',
                     'liquid_level_low_error', 'cooling_error',
                     'external_alarm_error', 'pump_overload_error',
                     'liquid_level_alarm_error', 'overtemperature_error',
                     'main_relay_missing_error', 'control_external',
                     'control_on', 'temperature']

    constant_variables = ['firmwareversion']

    urgent_variables = ['faultstatus', 'time', 'temperature_internal',
                        'temperature_external', 'pump_power']

    urgency_modulo = 10

    minimum_query_variables = ['firmwareversion', 'faultstatus', 'time', 'temperature_internal',
                               'temperature_external', 'pump_power',
                               'cooling_on', 'setpoint', 'date',
                               'fuzzycontrol',
                               'fuzzystatus', 'highlimit', 'lowlimit',
                               'diffcontrol_on', 'autostart', 'fuzzyid',
                               'beep', 'watchdog_on', 'watchdog_setpoint']

    backend_class = HaakePhoenix_Backend
