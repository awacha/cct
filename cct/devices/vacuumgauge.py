'''
Created on Oct 13, 2015

@author: labuser
'''
from .device import Device_TCP, DeviceError


class VacuumGauge(Device_TCP):

    log_formatstr = '{pressure}'

    def _query_variable(self, variablename):
        if variablename is None:
            variablenames = ['pressure', 'version', 'units']
        else:
            variablenames = [variablename]

        for vn in variablenames:
            if vn == 'pressure':
                self._send(b'001M^\r')
            elif vn == 'version':
                self._send(b'001Te\r')
            elif vn == 'units':
                self._send(b'001Uf\r')
            else:
                raise NotImplementedError(vn)

    def _process_incoming_message(self, message):
        if not (message.startswith(b'001') and message.endswith(b'\r')):
            raise DeviceError('Invalid message: %s' % str(message))
        message = message[:-1]
        if b'\r' in message:
            # if we got multiple replies in a single message, process each one
            # individually
            for m in message.split(b'\r'):
                self._process_incoming_message(m)
        if not (sum(message[0:-1]) % 64 + 64 == message[-1]):
            # checksum error
            raise DeviceError('Checksum error on message %s' % str(message))
        if message[3] == 77:  # M
            pressure = float(message[4:8]) * 10**(-23 + float(message[8:10]))
            if self._update_variable('pressure', pressure):
                if pressure > 1:
                    self._update_variable('_status', 'No vacuum')
                elif pressure > 0.1:
                    self._update_variable('_status', 'Medium vacuum')
                else:
                    self._update_variable('_status', 'Vacuum OK')

        elif message[3] == 84:  # T
            self._update_variable('version', str(message[4:10]))
        elif message[3] == 85:  # U
            self._update_variable('units', str(message[4:10]))
        else:
            raise DeviceError(
                'Unknown message code %s in message %s' % (chr(message[3]), str(message)))
