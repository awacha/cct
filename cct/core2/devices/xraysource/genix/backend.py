import struct
import time
from typing import Sequence, Any, List, Tuple

from ...device.backend import DeviceBackend, VariableType
from ...utils.modbus import ModbusTCP


class GeniXBackend(DeviceBackend, ModbusTCP):
    class Status(DeviceBackend.Status):
        off = 'off'
        standby = 'standby'
        low = 'standby'
        full = 'full power'
        warmup = 'warming up'
        poweringoff = 'turning off...'
        xraysoff = 'X-rays off'
        goingtostandby = 'going to standby...'
        goingtofull = 'ramping up...'
        unknown = 'unknown'

    varinfo = [DeviceBackend.VariableInfo('power', dependsfrom=[], timeout=10, vartype=VariableType.FLOAT),
               DeviceBackend.VariableInfo('ht', dependsfrom=['power'], vartype=VariableType.FLOAT),
               DeviceBackend.VariableInfo('current', dependsfrom=['power'], vartype=VariableType.FLOAT),
               DeviceBackend.VariableInfo('tubetime', timeout=1, dependsfrom=['tube_temperature'], vartype=VariableType.FLOAT),
               DeviceBackend.VariableInfo('statusbits', timeout=0.5, vartype=VariableType.STR),
               DeviceBackend.VariableInfo('shutter', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('remote_mode', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('xrays', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('conditions_auto', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('tube_power', dependsfrom=['statusbits'], vartype=VariableType.FLOAT),
               DeviceBackend.VariableInfo('faults', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('xray_light_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('shutter_light_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('sensor2_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('tube_position_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('vacuum_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('waterflow_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('safety_shutter_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('temperature_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('sensor1_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('relay_interlock_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('door_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('filament_fault', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('tube_warmup_needed', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('interlock', dependsfrom=['interlock_lowlevel'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('overridden', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('warmingup', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('goingtostandby', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('rampingup', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('poweringdown', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('interlock_lowlevel', dependsfrom=['statusbits'], vartype=VariableType.BOOL),
               DeviceBackend.VariableInfo('tube_temperature', timeout=1, vartype=VariableType.FLOAT),
               ]

    def _query(self, variablename: str):
        if variablename == 'statusbits':
            self.modbus_read_coils(210, 30)
        elif variablename == 'power':
            self.modbus_read_holding_registers(50, 2)
        elif variablename == 'tube_temperature':
            self.modbus_read_holding_registers(54, 3)
        else:
            raise ValueError(f'Cannot query variable {variablename} directly.')

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        # no need for this as the GeniX instrument gives one reply for one question.
        return [message], b''

    def interpretMessage(self, message: bytes, sentmessage: bytes):
#        self.debug(f'Got message {message}')
        funccode, data = self.modbus_unpack(message, struct.unpack('>H', sentmessage[:2])[0])
        if funccode == 1:  # read coils
            # we only read from coils 210 to 239, i.e. 30 coils. This needs 4 bytes.
            # each bit corresponds to one coil. Coil 210 is the LSB of the first byte, 217 is the MSB of the first byte
            # etc.
            if data[0] != 4:
                raise ValueError(f'Expected 4 bytes while reading coils, got {data[0]}.')
            if len(data) != 5:
                raise ValueError(f'Expected length of data 5, got {len(data)}.')
            nbytes, valuebits = struct.unpack('>BL', data)
            values = {}
            self.updateVariable('statusbits', valuebits)
            for variable, mask in [
                ('remote_mode', 0x01000000),  # coil 210
                ('xrays', 0x02000000),  # coil 211
                ('goingtostandby', 0x04000000),  # coil 212
                ('rampingup', 0x08000000),  # coil 213
                ('conditions_auto', 0x10000000),  # coil 214
                ('poweringdown', 0x20000000),  # coil 215
                ('warmingup', 0x40000000),  # coil 216
                ('tube_power', 0x80000000),  # coil 217
                # coil 218 unknown        0x00010000
                ('faults', 0x00020000),  # coil 219
                ('xray_light_fault', 0x00040000),  # coil 220
                ('shutter_light_fault', 0x00080000),  # coil 221
                ('sensor2_fault', 0x00100000),  # coil 222
                ('tube_position_fault', 0x00200000),  # coil 223
                ('vacuum_fault', 0x00400000),  # coil 224
                ('waterflow_fault', 0x00800000),  # coil 225
                ('safety_shutter_fault', 0x00000100),  # coil 226
                ('temperature_fault', 0x00000200),  # coil 227
                ('sensor1_fault', 0x00000400),  # coil 228
                ('relay_interlock_fault', 0x00000800),  # coil 229
                ('door_fault', 0x00001000),  # coil 230
                ('filament_fault', 0x00002000),  # coil 231
                ('tube_warmup_needed', 0x00004000),  # coil 232
                # coil 233 unknown        0x00008000
                # ('blink', 0x00000001),  # coil 234
                ('interlock_lowlevel', 0x00000002),  # coil 235
                ('shutter_closed', 0x00000004),  # coil 236
                ('shutter_open', 0x00000008),  # coil 237
                # coil 238 is unknown     0x00000010
                ('overridden', 0x00000020),  # coil 239
            ]:
                values[variable] = (valuebits & mask) != 0
                if variable not in ['interlock', 'shutter_closed', 'shutter_open', 'tube_power']:
                    # this variable does not need special attention
                    self.updateVariable(variable, values[variable])
            if values['shutter_closed'] and not values['shutter_open']:
                self.updateVariable('shutter', False)
            elif not values['shutter_closed'] and values['shutter_open']:
                self.updateVariable('shutter', True)
            else:
                # intermediate state, do nothing
                pass
            # interlock. Tricky thing because if the bit is
            # 1) constantly off: interlock broken (circuit error): shutter cannot be opened
            # 2) blinking with 0.5-1 Hz: interlock circuit OK but one switch is open: shutter cannot be opened
            # 3) constantly on: interlock ok, all switches closed, safe to open shutter
            #
            # Because of the above, if the bit is 0, interlock is off. If 1, we cannot be sure if it is OK.
            # We analyze the last change in the interlock_lowlevel
            if not values['interlock_lowlevel']:
                self.updateVariable('interlock', False)
            elif time.monotonic() - self.getVariable('interlock_lowlevel').lastchange > 3.0:
                # if the low-level interlock (which blinks) is True since at least 3 seconds, it is considered full-on.
                self.updateVariable('interlock', True)
            else:
                self.updateVariable('interlock', False)
            self.updateVariable('tube_power', 50.0 if values['tube_power'] else 30.0)  # 50 W or 30 W

            # set the power status variable
            self.updatePowerStatus()

        elif funccode == 3:  # read holding registers
            sentfunccode, sentdata = self.modbus_unpack(sentmessage)
            if sentfunccode != funccode:
                raise ValueError(
                    f'Sent message function code ({sentfunccode}) does not match that of the received one '
                    f'({funccode}).')
            regno, nregs = struct.unpack('>HH', sentdata)
            if regno == 50 and nregs == 2:
                # get HT and current
                if data[0] != 4:
                    raise ValueError(f'Expected 4 bytes in reply, got {data[0]}')
                nbytes, ht, current = struct.unpack('>BHH', data)
                self.updateVariable('ht', ht / 100.)
                self.updateVariable('current', current / 100)
                self.updateVariable('power', ht * current / 10000)
                self.updateVariable('__auxstatus__', f'{ht/100:.1f} kV; {current/100:.2f} mA')
            elif regno == 54 and nregs == 3:
                # get temperature and tube usage time
                if data[0] != 6:
                    raise ValueError(f'Expected 6 bytes in reply, got {data[0]}')
                nbytes, temperature, tube_minutes, tube_hours = struct.unpack('>BHHH', data)
                self.updateVariable('tubetime', tube_hours + tube_minutes / 60)
                self.updateVariable('tube_temperature', temperature / 10)
            else:
                raise ValueError(f'Invalid register span: first {regno}, count {nregs}')
        elif funccode == 5:  # write single coil reply
            if len(data) != 4:
                raise ValueError(f'Expected 4 bytes of data, got {len(data)} bytes.')
            coil, state = struct.unpack('>HH', data)
            if coil in [
                247,  # open shutter
                248,  # close shutter
                249,  # reset faults
                252,  # ramp up
                244,  # power off
                245,  # start warm-up
                246,  # stop warm-up
            ] and (state != 0):
                # these commands in the GeniX work on impulsions: set the coil to 1, it acknowledges it and then we set
                # the coil back to 0.
                self.modbus_set_coil(coil, False)
            elif coil in [
                250,  # standby mode
                251,  # X-rays on/off
            ]:
                # these commands are on/off, following the state of the respective coils. Do nothing.
                pass
        else:
            raise ValueError(f'Invalid function code: {funccode}')
        self.updatePowerStatus()

    def issueCommand(self, name: str, args: Sequence[Any]):
        if not self['remote_mode']:
            # the state of the generator can only be changed in remote mode.
            self.commandError(name, f'Cannot issue command {name}: the generator is not in remote mode')
            return
        if name == 'shutter':
            # open or close the shutter.
            if args[0]:
                # open the shutter
                if not self['interlock']:
                    # but only if the interlock permits it.
                    self.commandError(name, 'Cannot open shutter: interlock is not OK.')
                    return
                self.modbus_set_coil(247, True)
            else:
                # if False, close it
                self.modbus_set_coil(248, True)
            self.commandFinished(name, f'{"Opening" if args[0] else "Closing"} shutter.')
        elif name == 'reset_faults':
            # re-test fault conditions.
            self.modbus_set_coil(249, True)
            self.commandFinished(name, "Resetting faults.")
        elif name == 'xrays':
            # x-ray generator can always be turned on. But it can only be turned off if the power is zero.
            if (self['__status__'] != self.Status.off) and not bool(args[0]):
                self.commandError(name, 'Cannot turn off X-ray generator: tube power is not zero.')
                return
            self.modbus_set_coil(251, bool(args[0]))
            self.commandFinished(name, "Turning off X-ray generator")
        elif name == 'poweroff':
            # always allow powering off, except when warming up
            if self['__status__'] == self.Status.warmup:
                self.commandError(name, 'Cannot turn power of X-ray tube in the middle of the warm-up procedure.')
                return
            self.updateVariable('__status__', self.Status.poweringoff)
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(244, True)  # power off.
            self.commandFinished(name, "Powering off X-ray generator")
        elif name == 'standby':
            # can go to standby only if X-ray are on and not warming up
            if self['__status__'] in [self.Status.warmup, self.Status.xraysoff]:
                self.commandError(name, 'Cannot go to stand-by if X-rays are off or warming up.')
                return
            self.updateVariable('__status__', self.Status.goingtostandby)
            self.modbus_set_coil(250, True)  # Standby mode on
            self.commandFinished(name, 'Going to standby mode.')
        elif name == 'full_power':
            if self['__status__'] == self.Status.full:
                self.commandFinished(name, 'Already at full power')
            elif self['__status__'] != self.Status.standby:
                self.commandError(name, 'X-ray tube can only be put in full-power mode from stand-by.')
                return
            self.updateVariable('__status__', self.Status.goingtofull)
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(252, True)  # ramp up
            self.commandFinished(name, 'Going to full power mode')
        elif name == 'start_warmup':
            if self['__status__'] != self.Status.off:
                self.commandError(
                    name, 'Warm-up can only be started when the X-ray generator is on and the tube power is zero.')
                return
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(245, True)  # start warm-up
            self.commandFinished(name, 'Starting warm-up sequence.')
        elif name == 'stop_warmup':
            if self['__status__'] != self.Status.warmup:
                self.commandError(name, 'Not in a warm-up cycle.')
                return
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(246, True)  # stop warm-up
            self.modbus_set_coil(244, True)  # power off
            self.commandFinished(name, 'Stopping warm-up sequence.')
        else:
            self.commandError(name, 'Invalid command')

    def updatePowerStatus(self):
        try:
            if not self['xrays']:
                self.updateVariable('__status__', self.Status.xraysoff)
                if self.panicking == self.PanicState.Panicking:
                    super().doPanic()
            elif self['warmingup']:
                self.updateVariable('__status__', self.Status.warmup)
            elif self['goingtostandby']:
                self.updateVariable('__status__', self.Status.goingtostandby)
            elif self['rampingup']:
                self.updateVariable('__status__', self.Status.goingtofull)
            elif self['poweringdown']:
                self.updateVariable('__status__', self.Status.poweringoff)
            elif self['power'] == 9:
                self.updateVariable('__status__', self.Status.standby)
            elif self['power'] == self['tube_power']:
                self.updateVariable('__status__', self.Status.full)
            elif (self['ht'] == 0) and (self['current'] == 0):
                self.updateVariable('__status__', self.Status.off)
                if self.panicking == self.PanicState.Panicking:
                    self.modbus_set_coil(251, 0)  # turn X-rays off
            else:
                self.updateVariable('__status__', self.Status.unknown)
        except KeyError:
            # this can happen when not all variables have been queried yet
            pass

    def doPanic(self):
        self.panicking = self.PanicState.Panicking
        # close the shutter
        self.modbus_set_coil(247, False)
        self.modbus_set_coil(248, True)
        if self['__status__'] == self.Status.xraysoff:
            super().doPanic()
        elif self['__status__'] == self.Status.warmup:
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(246, True)  # stop warm-up
            self.modbus_set_coil(244, True)  # power off
        elif self['__status__'] == self.Status.goingtostandby:
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(244, True)  # power off
        elif self['__status__'] == self.Status.goingtofull:
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(252, False)  # ramp up off
            self.modbus_set_coil(244, True)  # power off
        elif self['__status__'] == self.Status.poweringoff:
            pass
        elif self['__status__'] == self.Status.standby:
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(244, True)  # power off
        elif self['__status__'] == self.Status.full:
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(252, False)  # ramp up off
            self.modbus_set_coil(244, True)  # power off
        elif self['__status__'] == self.Status.off:
            self.modbus_set_coil(251, False)  # turn X-rays off
            super().doPanic()
        elif self['__status__'] == self.Status.unknown:
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(252, False)  # ramp up off
            self.modbus_set_coil(244, True)  # power off
        elif (self['ht'] > 0) or (self['current'] > 0):
            self.modbus_set_coil(250, False)  # Standby mode off
            self.modbus_set_coil(252, False)  # ramp up off
            self.modbus_set_coil(244, True)  # power off
        else:
            # ht == 0, current == 0
            super().doPanic()
