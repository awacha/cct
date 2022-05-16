import datetime
from math import inf
from typing import Sequence, Any, Tuple, List

from ...device.backend import DeviceBackend, VariableType


class SchottKL2500LEDBackend(DeviceBackend):
    class Status(DeviceBackend.Status):
        LightsOn = 'Lights on'
        LightsOff = 'Lights off'
        ShutterClosed = 'Shutter closed'

    varinfo = [
        DeviceBackend.VariableInfo(name='brightness', dependsfrom=[], urgent=True, timeout=1.0, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='hardwareversion', dependsfrom=[], urgent=True, timeout=inf, vartype=VariableType.STR),
        DeviceBackend.VariableInfo(name='frontpanellockout', dependsfrom=[], urgent=True, timeout=1.0, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='protocolversion', dependsfrom=[], urgent=True, timeout=inf, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='shutter', dependsfrom=[], urgent=True, timeout=1.0, vartype=VariableType.BOOL),
        DeviceBackend.VariableInfo(name='temperature', dependsfrom=[], urgent=True, timeout=1.0, vartype=VariableType.FLOAT),
        ]

    maximumBrightness = 1000

    def _query(self, variablename: str):
        if variablename == 'brightness':
            self.enqueueHardwareMessage(b'0BR?;')
        elif variablename == 'hardwareversion':
            self.enqueueHardwareMessage(b'0ID?;')
        elif variablename == 'frontpanellockout':
            self.enqueueHardwareMessage(b'0LK?;')
        elif variablename == 'protocolversion':
            self.enqueueHardwareMessage(b'0PV?;')
        elif variablename == 'shutter':
            self.enqueueHardwareMessage(b'0SH?;')
        elif variablename == 'temperature':
            self.enqueueHardwareMessage(b'0TX?;')
        else:
            raise ValueError(f'Invalid variable {variablename}')

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        msgs = message.split(b';')
        return msgs[:-1], msgs[-1]

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        self.debug(f'Interpreting message: {message.decode("ascii")} (sent: {sentmessage.decode("ascii")[:-1]})')
        if sentmessage[:3] != message[:3]:
            raise RuntimeError(f'Reply received for message {sentmessage[1:3]} sent to unit {sentmessage[:1]} from unit {message[:1]} to command {message[1:3]}')
        if message[3:4] == b'!':
            # an error happened
            raise RuntimeError(f'Error message received from illumination source: {message}')
        if message[1:3] == b'BR':
            value = int(message[3:].decode('ascii'), base=16)
            self.updateVariable('brightness', value)
            self.updateVariable('__auxstatus__', str(value))
        elif message[1:3] == b'LK':
            self.updateVariable('frontpanellockout', bool(int(message[3:].decode('ascii'), base=16)))
        elif message[1:3] == b'PV':
            major = int(message[3:5].decode('ascii'), base=16)
            minor = int(message[5:].decode('ascii'), base=16)
            self.updateVariable('protocolversion', major+0.01*minor)
        elif message[1:3] == b'SH':
            self.updateVariable('shutter', bool(int(message[3:].decode('ascii'), base=16)))
        elif message[1:3] == b'TX':
            self.updateVariable('temperature', int(message[3:].decode('ascii'), base=16)*0.0625 - 273.15)
        else:
            raise RuntimeError(f'Reply received from illumination unit for unknown command: {message}')
        if (self['brightness'] > 0) and not self['shutter']:
            self.updateVariable('__status__', self.Status.LightsOn)
        elif (self['brightness'] == 0):
            self.updateVariable('__status__', self.Status.LightsOff)
        elif self['shutter']:
            self.updateVariable('__status__', self.Status.ShutterClosed)

    def issueCommand(self, name: str, args: Sequence[Any]):
        if name == 'shutter':
            if args[0]:
                self.enqueueHardwareMessage(b'0SH0001;')
                self.commandFinished(name, 'Closing shutter')
            else:
                self.enqueueHardwareMessage(b'0SH0000;')
                self.commandFinished(name, 'Opening shutter')
        elif name == 'set_brightness':
            value = int(args[0])
            if (value < 0) or (value > min(self.maximumBrightness, 0xFFFF)):
                self.commandError(name, 'Invalid brightness value')
            else:
                self.enqueueHardwareMessage(f'0BR{value:04X};'.encode('ascii'))
            self.commandFinished(name, f'Brightness set to {value}')
        elif name == 'set_full_brightness':
            self.enqueueHardwareMessage(b'0BRFFFF;')
            self.commandFinished(name, 'Full brightness selected')
        elif name == 'frontpanellockout':
            if args[0]:
                self.enqueueHardwareMessage(b'0LK0001;')
                self.commandFinished(name, 'Activating front panel lockout.')
            elif args[1]:
                self.enqueueHardwareMessage(b'0LK0000;')
                self.commandFinished(name, 'Deactivating front panel lockout.')
        else:
            self.commandFinished(name, 'Unknown command')

    def doPanic(self):
        self.panicking = self.PanicState.Panicking
        if self['__status__'] == self.Status.Running:
            self.enqueueHardwareMessage(b'0BR0000;')
            self.enqueueHardwareMessage(b'0LK0000;')
        else:
            super().doPanic()
