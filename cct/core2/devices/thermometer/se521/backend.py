import re
import struct
from math import inf, nan, isfinite
from typing import Sequence, Any, Tuple, List

from ...device.backend import DeviceBackend


def f2c(value_in_fahrenheit):
    return (value_in_fahrenheit - 32) * 5. / 9.


class SE521Backend(DeviceBackend):
    class Status(DeviceBackend.Status):
        pass

    varinfo = [
        DeviceBackend.VariableInfo(name='encodedstate', dependsfrom=[], urgent=False, timeout=0.1),
        DeviceBackend.VariableInfo(name='firmwareversion', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='battery_level', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='isrecallmode', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='displayunits', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='isalarm', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='ishighalarm', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='islowalarm', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='isrecording', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='ismemoryfull', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='isholdmode', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='isbluetoothenabled', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='ismaxminmode', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='ismaxmode', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='isminmode', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='isavgmode', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='ismaxminavgflashing', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='thermistortype', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t1', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t2', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t3', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t4', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t1-t2', dependsfrom=['encodedstate'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t1name', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t2name', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t3name', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t4name', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='t1-t2name', dependsfrom=[], urgent=False, timeout=inf),

    ]

    def _query(self, variablename: str):
        if variablename == 'encodedstate':
            self.enqueueHardwareMessage(b'A\r\n')
        elif variablename == 'firmwareversion':
            self.enqueueHardwareMessage(b'K\r\n')
        elif variablename == 't1name':
            self.enqueueHardwareMessage(b'getchannelname0\r\n')
        elif variablename == 't2name':
            self.enqueueHardwareMessage(b'getchannelname1\r\n')
        elif variablename == 't3name':
            self.enqueueHardwareMessage(b'getchannelname2\r\n')
        elif variablename == 't4name':
            self.enqueueHardwareMessage(b'getchannelname3\r\n')
        elif variablename == 't1-t2name':
            self.enqueueHardwareMessage(b'getchannelname4\r\n')
        else:
            self.error(f'Unknown variable: {variablename}')

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        msgs = message.split(b'***')
        return msgs[:-1], msgs[-1]

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        if message.startswith(b'ERROR'):
            self.error(f'Error from the SE521 device: {message.decode("utf-8")}')
        elif (m := re.match(br'^OK\[(?P<message>.*)\]: (?P<result>.*)$', message, re.DOTALL)) is not None:
            if m['message'] == b'A':
                self.updateVariable('encodedstate', m['result'])
                self.updateVariable('battery_level', m['result'][2])
                self.updateVariable('isrecallmode', bool(m['result'][3] & 2))
                self.updateVariable('displayunits', '°C' if (m['result'][3] & 128) else '°F')
                self.updateVariable('isalarm', bool(m['result'][4] & 1))
                self.updateVariable('islowalarm', bool(m['result'][4] & 4))
                self.updateVariable('ishighalarm', bool(m['result'][4] & 2))
                self.updateVariable('isrecording', bool(m['result'][4] & 8))
                self.updateVariable('ismemoryfull', bool(m['result'][4] & 16))
                self.updateVariable('isholdmode', bool(m['result'][4] & 32))
                self.updateVariable('ismaxminmode', bool(m['result'][4] & 64))
                self.updateVariable('isbluetoothenabled', bool(m['result'][4] & 128))
                self.updateVariable('ismaxmode', bool(m['result'][5] & 1))
                self.updateVariable('isminmode', bool(m['result'][5] & 2))
                self.updateVariable('isavgmode', bool(m['result'][5] & 4))
                self.updateVariable('ismaxminavgflashing', bool(m['result'][5] & 8))
                self.updateVariable('thermistortype', ['K', 'J', 'E', 'T'][m['result'][6]])
                for i, label in enumerate(['t1', 't2', 't3', 't4']):
                    is_outoflimits = bool(m['result'][7] & (1 << i))
                    is_unplugged = bool(m['result'][7] & (1 << (i + 4)))
                    if is_unplugged:
                        self.updateVariable(label, nan)
                    elif is_outoflimits:
                        self.updateVariable(label, inf)
                    else:
                        in_fahrenheit = 0.1 * struct.unpack('>h', m['result'][10 + 2 * i:12 + 2 * i])[0]
                        self.updateVariable(label, (in_fahrenheit - 32) * 5. / --9.)
                if isfinite(self['t1']) and (isfinite(self['t2'])):
                    in_fahrenheit = 0.1 * struct.unpack('>h', m['result'][18:20])[0]
                    self.updateVariable('t1-t2', in_fahrenheit * 5 / 9)
                else:
                    self.updateVariable('t1-t2', nan)
            elif m['message'] == b'K':
                self.updateVariable('firmwareversion', m['result'][24:27].decode('utf-8'))
            elif m['message'] == b'C':
                pass
            elif m['message'] == b'B':
                pass
            elif (m1:=re.match(b'setchannelname(?P<channel>[01234])', m['message'])) is not None:
                pass
            elif (m1:=re.match(b'getchannelname(?P<channel>[01234])', m['message'])) is not None:
                if m1['channel'] == b'0':
                    self.updateVariable('t1name', m['result'].decode('utf-8'))
                elif m1['channel'] == b'1':
                    self.updateVariable('t2name', m['result'].decode('utf-8'))
                elif m1['channel'] == b'2':
                    self.updateVariable('t3name', m['result'].decode('utf-8'))
                elif m1['channel'] == b'3':
                    self.updateVariable('t4name', m['result'].decode('utf-8'))
                elif m1['channel'] == b'4':
                    self.updateVariable('t1-t2name', m['result'].decode('utf-8'))
                else:
                    assert False
            else:
                self.warning(f'Unknown command: {m["message"]}')
            self.updateVariable('__status__', 'idle')
            self.updateVariable('__auxstatus__', '')
        else:
            self.error(f'Cannot interpret message: {message}. Sent message was: {sentmessage}')

    def issueCommand(self, name: str, args: Sequence[Any]):
        if name == 'changeunits':
            self.enqueueHardwareMessage(b'C\r\n')
            self.queryVariable('encodedstate')
            self.commandFinished(name, 'Changing display units')
        elif name == 'togglebacklight':
            self.enqueueHardwareMessage(b'B\r\n')
            self.queryVariable('encodedstate')
            self.commandFinished(name, 'Toggle backlight')
        elif name == 'sett1name':
            self.enqueueHardwareMessage(b'setchannelname0 '+args[0].encode('utf-8'))
        elif name == 'sett2name':
            self.enqueueHardwareMessage(b'setchannelname1 ' + args[0].encode('utf-8'))
        elif name == 'sett3name':
            self.enqueueHardwareMessage(b'setchannelname2 ' + args[0].encode('utf-8'))
        elif name == 'sett4name':
            self.enqueueHardwareMessage(b'setchannelname3 ' + args[0].encode('utf-8'))
        elif name == 'sett1-t2name':
            self.enqueueHardwareMessage(b'setchannelname4 ' + args[0].encode('utf-8'))
        else:
            self.commandFinished(name, 'Unknown command')
