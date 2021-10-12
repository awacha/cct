import struct
from typing import Sequence, Any, List, Tuple

import numpy as np

from ...device.backend import DeviceBackend
from ...utils.modbus import ModbusTCP


class BT100SBackend(DeviceBackend, ModbusTCP):
    class Status(DeviceBackend.Status):
        stopped = 'stopped'
        running = 'running'

    varinfo = [DeviceBackend.VariableInfo('rotating_speed_timer', timeout=1, dependsfrom=None),
               DeviceBackend.VariableInfo('steps_for_one_round', timeout=np.inf, dependsfrom=['rotating_speed_timer']),
               DeviceBackend.VariableInfo('analog_speed_control', timeout=np.inf, dependsfrom=['rotating_speed_timer']),
               DeviceBackend.VariableInfo('manufacturer', timeout=np.inf, dependsfrom=['rotating_speed_timer']),
               DeviceBackend.VariableInfo('product', timeout=np.inf, dependsfrom=['rotating_speed_timer']),
               DeviceBackend.VariableInfo('keyvalue', timeout=1, dependsfrom=None),
               DeviceBackend.VariableInfo('easydispense', timeout=np.inf, dependsfrom=['keyvalue']),
               DeviceBackend.VariableInfo('timedispense', timeout=np.inf, dependsfrom=['keyvalue']),
               DeviceBackend.VariableInfo('rotating_speed', timeout=1, dependsfrom=None),
               DeviceBackend.VariableInfo('direction', timeout=np.inf, dependsfrom=['rotating_speed']),
               DeviceBackend.VariableInfo('running', timeout=np.inf, dependsfrom=['rotating_speed']),
               DeviceBackend.VariableInfo('fullspeed', timeout=np.inf, dependsfrom=['rotating_speed']),
               DeviceBackend.VariableInfo('control_mode', timeout=np.inf, dependsfrom=['rotating_speed']),
               DeviceBackend.VariableInfo('easy_dispense_volume', timeout=np.inf, dependsfrom=['rotating_speed']),
               DeviceBackend.VariableInfo('dispense_time', timeout=np.inf, dependsfrom=['rotating_speed']),
               DeviceBackend.VariableInfo('littleendian', timeout=np.inf, dependsfrom=['rotating_speed']),
               DeviceBackend.VariableInfo('modbusaddress', timeout=np.inf, dependsfrom=['rotating_speed']),
               ]

    def enqueueHardwareMessage(self, message: bytes, numreplies: int = 1, urgencymodifier: float = 0.0):
        super().enqueueHardwareMessage(message, numreplies, urgencymodifier)

    def _query(self, variablename: str):
        if variablename == 'rotating_speed_timer':
            self.modbus_read_input_registers(1000, 30)
        elif variablename == 'keyvalue':
            self.modbus_read_holding_registers(3000, 3)
        elif variablename == 'rotating_speed':
            self.modbus_read_holding_registers(3100, 10)
        else:
            raise ValueError(f'Cannot query variable {variablename} directly.')

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        # no need for this as the Modbus protocol gives one reply for one question.
        return [message], b''

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        funccode, data = self.modbus_unpack(message, struct.unpack('>H', sentmessage[:2])[0])
        sentfunccode, sentdata = self.modbus_unpack(sentmessage)
        if sentfunccode != funccode:
            raise ValueError(
                f'Sent message function code ({sentfunccode}) does not match that of the received one '
                f'({funccode}).')
        if (funccode == 3) or (funccode == 4):  # read holding/input registers
            regno, nregs = struct.unpack('>HH', sentdata)
            if data[0] != nregs * 2:
                raise ValueError(f'Expected {nregs * 2} bytes in reply, got {data[0]}')
            nbytes, *values = struct.unpack('>B' + 'H' * (data[0] // 2), data)
            if regno == 1000 and nregs == 30:
                self.updateVariable('rotating_speed_timer', values[1])
                self.updateVariable('steps_for_one_round', values[2])
                self.updateVariable('analog_speed_control', values[3] / 10.)
                self.updateVariable('manufacturer',
                                    struct.pack('<HHHHH', *values[18:23]).replace(b'\x00', b'').decode('ascii'))
                self.updateVariable('product',
                                    struct.pack('<HHHHH', *values[23:28]).replace(b'\x00', b'').decode('ascii'))
            elif regno == 3000 and nregs == 3:
                self.updateVariable('keyvalue', values[0])
                self.updateVariable('easydispense', bool(values[1]))
                self.updateVariable('timedispense', bool(values[2]))
            elif regno == 3100 and nregs == 10:
                self.updateVariable('rotating_speed', values[0] / 10.0)
                self.updateVariable('direction', 'counterclockwise' if bool(values[1]) else 'clockwise')
                self.updateVariable('running', bool(values[2]))
                self.updateVariable('fullspeed', bool(values[3]))
                self.updateVariable('control_mode', ['internal', 'external', 'footswitch', 'logic level', 'logic level 2'][values[4]])
                self.updateVariable('modbusaddress', values[7])
                self.updateVariable('littleendian', bool(values[8]))
                self.updateVariable('dispense_time', values[9] / 10.)
                if self['littleendian']:
                    self.updateVariable('easy_dispense_volume', values[5] + 0x10000 * values[6])
                else:
                    self.updateVariable('easy_dispense_volume', values[6] + 0x10000 * values[5])
            else:
                raise ValueError(f'Invalid register span: first {regno}, count {nregs}')
        elif funccode == 6:  # write holding register result
            regrec, newvaluerec = struct.unpack('>HH', data)
            regsent, newvaluesent = struct.unpack('>HH', sentdata)
            if (regrec != regsent) or (newvaluerec != newvaluesent):
                raise ValueError(
                    f'Invalid message received for write holding register function: '
                    f'{regsent=}, {regrec=}, {newvaluesent=}, {newvaluerec=}')
            elif (regrec == 3102) and (newvaluerec == 1):
                self.commandFinished('start', 'Started pump')
            elif (regrec == 3102) and (newvaluerec == 1):
                self.commandFinished('start', 'Started pump')
        else:
            raise ValueError(f'Invalid function code: {funccode}')

    def issueCommand(self, name: str, args: Sequence[Any]):
        if name == 'start':
            self.modbus_write_register(3102, 1)
            self.queryVariable('running', True)
        elif name == 'stop':
            self.modbus_write_register(3102, 0)
            self.queryVariable('running', True)
        elif name == 'clockwise':
            self.modbus_write_register(3101, 0)
            self.queryVariable('direction', True)
        elif name == 'counterclockwise':
            self.modbus_write_register(3101, 1)
            self.queryVariable('direction', True)
        elif name == 'setspeed':
            self.modbus_write_register(3100, int(args[0] * 10))
            self.queryVariable('rotating_speed', True)
        elif name == 'fullspeed':
            self.modbus_write_register(3103, 1)
            self.queryVariable('fullspeed', True)
        elif name == 'normalspeed':
            self.modbus_write_register(3103, 0)
            self.queryVariable('fullspeed', True)
        elif name == 'internal_control':
            self.modbus_write_register(3104, 0)
            self.queryVariable('control_mode', True)
        elif name == 'external_control':
            self.modbus_write_register(3104, 1)
            self.queryVariable('control_mode', True)
        elif name == 'footswitch_control':
            self.modbus_write_register(3104, 2)
            self.queryVariable('control_mode', True)
        elif name == 'logic_level_control':
            self.modbus_write_register(3104, 3)
            self.queryVariable('control_mode', True)
        elif name == 'logic_level_2_control':
            self.modbus_write_register(3104, 3)
            self.queryVariable('control_mode', True)
        elif name == 'set_easy_dispense_mode':
            self.modbus_write_register(3001, int(bool(args[0])))
            self.queryVariable('easydispense', True)
        elif name == 'set_time_dispense_mode':
            self.modbus_write_register(3002, int(bool(args[0])))
            self.queryVariable('timedispense', True)
        elif name == 'set_easy_dispense_volume':
            self.modbus_write_registers(3105, [int(args[0]) % 65536, int(args[0]) // 65536])
        elif name == 'set_dispense_time':
            self.modbus_write_register(3109, int(args[0] * 10))
            self.queryVariable('dispense_time', True)
        else:
            raise ValueError(f'Unknown command: {name}')
        self.commandFinished(name, 'OK')
