# DATAQ DI-149 USB data acquisition unit

import re
from typing import Dict, Callable, Any

from .device.device_tcp import DeviceBackend_TCP
from .device.exceptions import ReadOnlyVariable, UnknownVariable, UnknownCommand
from .device.frontend import Device, DeviceError


class DATAQ_DI_149_Backend(DeviceBackend_TCP):
    _rate_ranges={10000:1,
                  5000:2,
                  2000:3,
                  1000:4,
                  500:5,
                  200:6,
                  100:7,
                  50:8,
                  20:9,
                  10:10,
                  5:11,}
    _rate_range = 10000
    _samples_per_min=50
    _minimum_scan_points = 100

    def initialize_after_connect(self):
        self._stored_message=b''
        self._initialize_device()
        self._initializing=True
        self._initialize_scan_list()

    def set_variable(self, variable: str, value: object):
        raise ReadOnlyVariable(variable)

    def query_variable(self, variablename: str):
        if variablename.startswith('info_'):
            try:
                idx = int(variablename.split('_',1)[1])
            except (IndexError,ValueError):
                raise UnknownVariable(variablename)
            self.send_message(b'info {:d}\x0d'.format(idx), expected_replies=1, asynchronous=False)
        elif variablename in ['comm_mode', 'scan_rate_raw', 'rate', 'rate_raw', 'counter'] or variablename.startswith('slist_'):
            return True
        else:
            raise UnknownVariable(variablename)
        return True

    def get_complete_messages(self, message:bytes):
        return [message,b'']

    def _initialize_device(self):
        self.send_message(b'stop\x0dasc\x0dreset 1\x0dslist 0 xffff\x0dbin\x0d', expected_replies=5)

    def _initialize_scan_list(self):
        commands=['asc'] # set ASCII mode
        for i in range(9):
            # append reading command for the i-th analog input (i=8 is the digital input)
            commands.append('slist {0:d} x{0:04x}'.format(i))
        commands.append('slist 9 x0{:x}095'.format(self._rate_ranges[self._rate_range])) # rate counter on DI2
        commands.append('slist 10 x000a') # counter on DI3
        srate = 75000//self._samples_per_min
        if srate <75:
            raise DeviceError('Too high sample rate (srate <75)')
        elif srate >65535:
            raise DeviceError('Too low sample rate (srate >65535')
        commands.append('srate {:d}'.format(int(srate)))
        commands.append('bin')
        self.send_message(b'\r'.join([c.encode('ascii')+b'\xd0' for c in commands]))

    def _start_scan(self):
        if self.is_busy():
            raise DeviceError('Cannot start scan: already scanning')
        self.busysemaphore.acquire()
        self.send_message(b'start\x0d')

    def _stop_scan(self):
        self.send_message(b'stop\x0d')

    @staticmethod
    def match_re_on_message(regex: bytes, message:bytes,
                            updatefunction:Callable[[Dict[str, bytes]], Any]) -> bytes:
        m = re.match(regex, message)
        if m is None:
            return message
        else:
            updatefunction(m.groupdict())
            return message[m.span()[1]:]

    def _process_info_message(self, groupdict:Dict[str,bytes]):
        return self.update_variable('info_{}'.format(groupdict['num']),groupdict['info'])

    def _process_stopped_message(self, groupdict:Dict[str, bytes]):

        self.busysemaphore.release()
        return True

    def _process_started_message(self, groupdict:Dict[str, bytes]):
        self._scan=[]
        self.busysemaphore.release()
        return True

    def _process_slist_message(self, groupdict:Dict[str, bytes]):
        return self.update_variable('slist_{}'.format(groupdict['num']), groupdict['listitem'])

    def _process_asc_message(self, groupdict:Dict[str, bytes]):
        return self.update_variable('comm_mode','asc')

    def _process_bin_message(self, groupdict:Dict[str, bytes]):
        return self.update_variable('comm_mode','bin')

    def _process_reset_message(self, groupdict:Dict[str, bytes]):
        return True

    def _process_srate_message(self, groupdict:Dict[str, bytes]):
        return self.update_variable('scan_rate_raw',int(groupdict['rate']))

    def _unpack_number(self, num:bytes):
        value=(((num[1]^128)>>1)<<5)+(num[0]>>3)
        if (value & (1<<(11)) ) !=0:
             value = value - (1<<12)
        return bool(num[0]&2), bool(num[0]&4), value

    def _unpack_digital_in(self, num:bytes):
        return bool(num[0]& 128), bool(num[1] & 2), bool(num[1] & 4), bool(num[1] & 8)

    def _unpack_rate_and_counter(self, num:bytes):
        return ((num[1]>>1)<<7)+(num[0]>>1)

    def _unpack_scan_point(self, message:bytes):
        if message[0] & 1:
            raise ValueError('Invalid message, LSB of the first byte is not zeroed.')
        self._scan.append([self._unpack_number(message[2*i:2*i+2])[2] for i in range(8)])
        d1, d2, d3, d4 = self._unpack_digital_in(message[16:18])
        rate = self._unpack_rate_and_counter(message[18:20])
        self.update_variable('rate_raw', rate)
        rate = self._rate_range*rate/16384
        self.update_variable('rate',rate)
        self.update_variable('counter', self._unpack_rate_and_counter(message[20:22]))

    def process_incoming_message(self, message, original_sent=None):
        try:
            message = self._stored_message + message
        except AttributeError:
            pass
        self._stored_message=b''
        if self.is_busy():
            if message.startswith(b'stop\r'):
                self._process_stopped_message({})
                message=message[4:]
            elif len(message)>=22:
                # a little-endian byte stream ensues. The least significant bit of the first byte is 0,
                # all subsequent bytes has this set as 1. The bit assignments are:
                # Byte #1:   A4   A3   A2   A1   A0   D1   D0   sync==0    -> number A
                # Byte #2:  A11  A10   A9   A8   A7   A6   A5   sync==1    -> number A
                # Byte #3:   B4   B3   B2   B1   B0   D1   D0   sync==1    -> number B
                # Byte #4:  B11  B10   B9   B8   B7   B6   B5   sync==1    -> number B
                #  ... etc. for all the numbers.
                # Bits X11-X0 are 2-s component encoded numbers after flipping bit #11.
                # D0 and D1 are digital inputs 0 and 1.
                scanpoint=message[:22]
                message=message[22:]
        else:
            for regex, func in [
                (b'^info (?P<num>\d+) (?P<info>[\d\w]+)\r', self._process_info_message),
                (b'^stop\r', self._process_stopped_message),
                (b'^start\r', self._process_started_message),
                (b'^slist (?P<num>\d+) (?P<listitem>x[0-9a-f]{4})\r', self._process_slist_message),
                (b'^asc\r', self._process_asc_message),
                (b'^bin\r', self._process_bin_message),
                (b'^reset (?P<resetidx>\d+)', self._process_reset_message), # no \r at the end of the message!
                (b'^srate (?P<rate>\d+)\r', self._process_srate_message),
                ]:
                message=self.match_re_on_message(regex, message, func)
                if not message:
                    break
        self._stored_message=message

    def execute_command(self, commandname: str, arguments: tuple):
        """TPG201 does not implement any commands"""
        raise UnknownCommand(commandname)


class DATAQ_DI_149(Device):
    log_formatstr = ''

    watchdog_timeout = 7

    reply_timeout = 5

    idle_wait = 2

    minimum_query_variables = ['info_0', 'info_1','info_2', 'info_3', 'info_4','info_5','info_6']

    all_variables = ['info_0', 'info_1', 'info_2', 'info_3', 'info_4', 'info_5', 'info_6',
                     'comm_mode', 'scan_rate_raw', 'slist_0', 'slist_1', 'slist_2', 'slist_3',
                     'slist_4', 'slist_5', 'slist_6', 'slist_7', 'slist_8', 'slist_9', 'slist_10',
                     'rate_raw', 'rate', 'counter'
                     ]

    no_log_variables = ['comm_mode']

    constant_variables = ['info_0', 'info_1', 'info_2', 'info_3', 'info_4', 'info_5', 'info_6',
                          'comm_mode', 'scan_rate_raw', 'slist_0', 'slist_1', 'slist_2', 'slist_3',
                     'slist_4', 'slist_5', 'slist_6', 'slist_7', 'slist_8', 'slist_9', 'slist_10',
                          'rate_raw', 'counter', 'rate']

    backend_class = DATAQ_DI_149_Backend
