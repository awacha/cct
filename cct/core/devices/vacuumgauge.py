'''
Created on Oct 13, 2015

@author: labuser
'''
import logging

from .device import Device_TCP, DeviceError, UnknownVariable

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class TPG201(Device_TCP):

    log_formatstr = '{pressure}'

    _all_variables = ['pressure', 'version', 'units']

    _minimum_query_variables = ['pressure', 'version', 'units']

    def _has_all_variables(self):
        return all([v in self._properties for v in ['pressure','version','units','_status']])

    def _query_variable(self, variablename, minimum_query_variables=None):
        if not super()._query_variable(variablename):
            return
        if variablename == 'pressure':
            self._send(b'001M^\r')
        elif variablename == 'version':
            self._send(b'001Te\r')
        elif variablename == 'units':
            self._send(b'001Uf\r')
        else:
            raise UnknownVariable(variablename)

    def _get_complete_messages(self, message):
        messages = message.split(b'\r')
        for i in range(len(messages) - 1):
            messages[i] = messages[i] + b'\r'
        return messages

    def _process_incoming_message(self, message, original_sent=None):
        # The TPG-201 Pirani Gauge always gives exactly 1 reply for each
        # sent message, therefore we are safe to release the cleartosend
        # semaphore at this point, so while we are handling this message,
        # the sending process can commence sending the next message.
        self._cleartosend_semaphore.release()
        if not (message.startswith(b'001') and message.endswith(b'\r')):
            raise DeviceError('Invalid message: %s' % str(message))
        message = message[:-1]
        if not (sum(message[0:-1]) % 64 + 64 == message[-1]):
            # checksum error
            raise DeviceError('Checksum error on message %s' % str(message))
        if message[3] == 77:
            # The 4th character of the message is an M. Note that message[3]
            # has a type of int, thus it cannot be equal to b'M'.
            pressure = float(message[4:8]) * 10**(-23 + float(message[8:10]))
            if self._update_variable('pressure', pressure):
                if pressure > 1:
                    self._update_variable('_status', 'No vacuum')
                elif pressure > 0.1:
                    self._update_variable('_status', 'Medium vacuum')
                else:
                    self._update_variable('_status', 'Vacuum OK')
                self._update_variable('_auxstatus', '%.2f mbar'%pressure)
        elif message[3] == 84:  # T
            self._update_variable('version', str(message[4:10]))
        elif message[3] == 85:  # U
            self._update_variable('units', str(message[4:10]))
        else:
            raise DeviceError(
                'Unknown message code %s in message %s' % (chr(message[3]), str(message)))
