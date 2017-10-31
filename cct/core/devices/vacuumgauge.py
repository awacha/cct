"""
Created on Oct 13, 2015

@author: labuser
"""
import logging

from .device import DeviceBackend_TCP, DeviceError, UnknownVariable, Device, UnknownCommand, ReadOnlyVariable

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# noinspection PyPep8Naming
class TPG201_Backend(DeviceBackend_TCP):
    invalid_characters = [b'\xc6', b'\xbe']

    def set_variable(self, variable: str, value: object):
        raise ReadOnlyVariable(variable)

    def query_variable(self, variablename: str):
        if variablename == 'pressure':
            self.send_message(b'001M^\r', expected_replies=1, asynchronous=False)
        elif variablename == 'version':
            self.send_message(b'001Te\r', expected_replies=1, asynchronous=False)
        elif variablename == 'units':
            self.send_message(b'001Uf\r', expected_replies=1, asynchronous=False)
        else:
            raise UnknownVariable(variablename)
        return True

    def get_complete_messages(self, message: bytes):
        messages = message.split(b'\r')
        for i in range(len(messages) - 1):
            messages[i] = messages[i] + b'\r'
        return messages

    def process_incoming_message(self, message: bytes, original_sent=None):
        for c in self.invalid_characters:
            message = message.replace(c, b'')
        if not (message.startswith(b'001') and message.endswith(b'\r')):
            raise DeviceError('Invalid message: ' + str(message))
        message = message[:-1]
        if not (sum(message[0:-1]) % 64 + 64 == message[-1]):
            # checksum error
            raise DeviceError('Checksum error on message ' + str(message))
        if message[3] == 77:
            # The 4th character of the message is an M. Note that message[3]
            # has a type of int, thus it cannot be equal to b'M'.
            pressure = float(message[4:8]) * 10 ** (-23 + float(message[8:10]))
            if self.update_variable('pressure', pressure):
                if pressure > 1:
                    self.update_variable('_status', 'No vacuum')
                elif pressure > 0.1:
                    self.update_variable('_status', 'Medium vacuum')
                else:
                    self.update_variable('_status', 'Vacuum OK')
                self.update_variable('_auxstatus', '{:.3f} mbar'.format(pressure))
        elif message[3] == 84:  # T
            self.update_variable('version', message[4:10].decode('ascii'))
        elif message[3] == 85:  # U
            self.update_variable('units', message[4:10].decode('ascii'))
        else:
            raise DeviceError(
                'Unknown message code {} in message {}'.format(chr(message[3]), str(message)))

    def execute_command(self, commandname: str, arguments: tuple):
        """TPG201 does not implement any commands"""
        raise UnknownCommand(commandname)


class TPG201(Device):
    log_formatstr = '{pressure:.3f}'

    all_variables = ['pressure', 'version', 'units']

    minimum_query_variables = ['pressure', 'version', 'units']

    backend_class = TPG201_Backend

    urgency_modulo = 10

    urgent_variables = ['pressure']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loglevel = logger.level
