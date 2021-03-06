import logging
import time
from typing import Optional

from .device import Device, DeviceBackend_ModbusTCP, DeviceError, InvalidMessage, ReadOnlyVariable, UnknownCommand, \
    UnknownVariable

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# noinspection PyPep8Naming
class GeniX_Backend(DeviceBackend_ModbusTCP):
    _interlock_fixing_time = 3  # time to ascertain if the interlock is really OK.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lasttimes['readstatus'] = 0
        self.lasttimes['interlock_change'] = 0

    def query_variable(self, variablename: str):
        if variablename == 'power':
            try:
                self.update_variable('power', self.properties['ht'] * self.properties['current'])
            except KeyError:
                return False
        elif variablename == 'ht':
            ht = self.read_integer(50) / 100
            self.update_variable('ht', ht)
            try:
                self.update_variable('_auxstatus',
                                     '{:.2f} kV, {:.2f} mA'.format(self.properties['ht'], self.properties['current']))
            except KeyError:
                pass
        elif variablename == 'current':
            current = self.read_integer(51) / 100
            self.update_variable('current', current)
            try:
                self.update_variable('_auxstatus',
                                     '{:.2f} kV, {:.2f} mA'.format(self.properties['ht'], self.properties['current']))
            except KeyError:
                pass
        elif variablename == 'tubetime':
            self.update_variable('tubetime', (self.read_integer(55) / 60.0 + self.read_integer(56)))
        elif variablename in ['shutter', 'remote_mode', 'xrays', 'conditions_auto',
                              'tube_power', 'faults', 'xray_light_fault',
                              'shutter_light_fault', 'sensor2_fault',
                              'tube_position_fault', 'vacuum_fault',
                              'waterflow_fault', 'safety_shutter_fault',
                              'temperature_fault', 'sensor1_fault',
                              'relay_interlock_fault', 'door_fault',
                              'filament_fault', 'tube_warmup_needed',
                              'interlock', 'overridden', '_status', 'warmingup', 'goingtostandby', 'rampingup',
                              'poweringdown']:
            statusbits = self.read_coils(210, 36)
            self.lasttimes['readstatus'] = time.monotonic()
            self.update_variable('remote_mode', statusbits[0])
            self.update_variable('xrays', statusbits[1])
            if not statusbits[1]:
                if self.update_variable('_status', 'X-rays off'):
                    self.logger.info('X-rays turned off.')
            self.update_variable('goingtostandby', statusbits[2])
            if statusbits[2]:
                if self.update_variable('_status', 'Going to stand-by'):
                    self.logger.info('Putting X-ray tube into stand-by mode.')
            self.update_variable('rampingup', statusbits[3])
            if statusbits[3]:
                if self.update_variable('_status', 'Ramping up'):
                    self.logger.info('Ramping up X-ray tube power.')
            self.update_variable('conditions_auto', statusbits[4])
            self.update_variable('poweringdown', statusbits[5])
            if statusbits[5]:
                if self.update_variable('_status', 'Powering down'):
                    self.logger.info('Powering down X-ray tube')
            self.update_variable('warmingup', statusbits[6])
            if statusbits[6]:
                if self.update_variable('_status', 'Warming up'):
                    self.logger.info('X-ray tube warm-up started.')
            self.update_variable('tube_power', [30, 50][statusbits[7]])
            # statusbits[8] is unknown
            self.update_variable('faults', statusbits[9])
            self.update_variable('xray_light_fault', statusbits[10])
            self.update_variable('shutter_light_fault', statusbits[11])
            self.update_variable('sensor2_fault', statusbits[12])
            self.update_variable('tube_position_fault', statusbits[13])
            self.update_variable('vacuum_fault', statusbits[14])
            self.update_variable('waterflow_fault', statusbits[15])
            self.update_variable('safety_shutter_fault', statusbits[16])
            self.update_variable('temperature_fault', statusbits[17])
            self.update_variable('sensor1_fault', statusbits[18])
            self.update_variable('relay_interlock_fault', statusbits[19])
            self.update_variable('door_fault', statusbits[20])
            self.update_variable('filament_fault', statusbits[21])
            self.update_variable('tube_warmup_needed', statusbits[22])
            # statusbits[23] is unknown
            # statusbits[24] is just an 1Hz pulse signal
            # statusbits[25] is the interlock. It is tricky, because three
            # situations can exist:
            # 1) constantly False: interlock is broken, because of a fault.
            #     The shutter cannot be opened in this case.
            # 2) constantly True: interlock is set, shutter can be opened.
            # 3) alternating between True and False with 1 Hz: this is the
            #     case when the safety circuit (door interlock) is not closed.
            #
            # We have an interlock_lowlevel variable, which carries the most
            # recent reading on statusbits[25]. The `interlock` variable is
            # adjusted in a way that it is False in case 1) and 3) above, and
            # only true in the case 2).
            if self.update_variable('interlock_lowlevel', statusbits[25]):
                self.lasttimes['interlock_change'] = time.monotonic()
            if statusbits[25]:
                if time.monotonic() - self.lasttimes['interlock_change'] > self._interlock_fixing_time:
                    # if a given amount of time has elapsed since we have
                    # last seen an interlock broken state, this means that
                    # we are truly in interlock OK state.
                    self.update_variable('interlock', True)
                    # otherwise do nothing.
            else:
                # if interlock_lowlevel signals Broken, set interlock to broken.
                self.update_variable('interlock', False)
            if statusbits[26] and not statusbits[27]:
                if self.update_variable('shutter', False):
                    self.logger.info('Beam shutter is closed.')
            elif statusbits[27] and not statusbits[26]:
                if self.update_variable('shutter', True):
                    self.logger.info('Beam shutter is open.')
            else:
                # do nothing, we are in an intermediate state between open and
                # closed, i.e. the shutter is just opening or closing.
                pass
            # statusbits[28] is unknown
            self.update_variable('overridden', statusbits[29])
            try:
                if statusbits[1]:  # X-rays ON
                    if not (statusbits[2] or statusbits[3] or statusbits[5] or statusbits[6]):
                        # if not going to standby, not ramping up,
                        # not powering down and not warming up, decide the
                        # value of _status by the current output power
                        if self.properties['ht'] == 0 and self.properties['current'] == 0:
                            if self.update_variable('_status', 'Power off'):
                                self.logger.info('X-ray tube powered off')
                        elif self.properties['power'] == 9:
                            if self.update_variable('_status', 'Low power'):
                                self.logger.info('X-ray tube is now in stand-by mode.')
                        elif self.properties['power'] == 30:
                            if self.update_variable('_status', 'Full power'):
                                self.logger.info('X-ray tube is now in full-power mode.')
            except KeyError:
                pass
        else:
            raise UnknownVariable(variablename)
        return True

    def execute_command(self, commandname, arguments):
        if commandname == 'shutter':
            self.write_coil(247 + int(not arguments[0]), True)
            self.write_coil(247 + int(not arguments[0]), False)
            time.sleep(0.5)
            self.queryone('shutter', force=True)
        elif commandname == 'poweroff':
            self.write_coil(250, False)  # Not standby
            # Pulse the power-off coil
            self.write_coil(244, True)
            self.write_coil(244, False)
            self.queryone('_status', force=True)
        elif commandname == 'xrays':
            self.write_coil(251, bool(arguments[0]))
            self.queryone('xrays', force=True)
        elif commandname == 'reset_faults':
            # Pulse the reset_faults coil
            self.write_coil(249, True)
            self.write_coil(249, False)
            self.queryone('faults', force=True)
        elif commandname == 'start_warmup':
            self.write_coil(250, False)  # Not standby
            # Pulse the start warmup coil
            self.write_coil(245, True)
            self.write_coil(245, False)
            self.queryone('_status', force=True)
        elif commandname == 'stop_warmup':
            self.write_coil(250, False)  # Not standby
            # Pulse the stop warmup coil
            self.write_coil(246, True)
            self.write_coil(246, False)
            self.queryone('_status', force=True)
        elif commandname == 'standby':
            self.write_coil(250, True)  # Standby
            self.queryone('_status', force=True)
        elif commandname == 'full_power':
            self.write_coil(250, False)  # Not standby
            # Pulse the full-power coil
            self.write_coil(252, True)
            self.write_coil(252, False)
            self.queryone('_status', force=True)
        else:
            raise UnknownCommand(commandname)

    def get_telemetry(self):
        tm = super().get_telemetry()
        tm.last_readstatus = time.monotonic() - self.lasttimes['readstatus']
        return tm

    def set_variable(self, variable: str, value: object):
        raise ReadOnlyVariable(variable)

    def process_incoming_message(self, message: bytes, original_sent: bytes = None):
        # we communicate synchronously with the ModbusTCP device in query_variable() and execute_command()
        raise InvalidMessage(message)


class GeniX(Device):
    log_formatstr = '{_status}\t{ht}\t{current}\t{shutter}'

    all_variables = ['ht', 'current', 'tubetime', 'shutter', 'power', 'remote_mode', 'xrays', 'conditions_auto',
                     'tube_power', 'faults', 'xray_light_fault',
                     'shutter_light_fault', 'sensor2_fault',
                     'tube_position_fault', 'vacuum_fault',
                     'waterflow_fault', 'safety_shutter_fault',
                     'temperature_fault', 'sensor1_fault',
                     'relay_interlock_fault', 'door_fault',
                     'filament_fault', 'tube_warmup_needed',
                     'interlock', 'overridden', 'warmingup', 'goingtostandby', 'rampingup', 'poweringdown']

    minimum_query_variables = ['ht', 'current', 'tubetime', 'shutter', 'power']

    backend_interval = 0.3

    backend_class = GeniX_Backend

    last_powered = 0

    last_warmup = 0

    no_log_variables = ['interlock_lowlevel']

    queryall_interval = 0.7

    warmup_interval = 24 * 3600

    _warmup_stop_forced = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loglevel = logger.level

    def shutter(self, requested_status: Optional[bool] = None):
        """Open or close the shutter"""
        if requested_status is None:
            return self.get_variable('shutter')
        else:
            self.execute_command('shutter', requested_status)

    def reset_faults(self):
        """Try to reset faults."""
        self.execute_command('reset_faults')

    def set_xrays(self, on: bool):
        """Turn X-ray generator on or off"""
        self.execute_command('xrays', on)

    def is_busy(self, status=None):
        if status is None:
            status = self.get_variable('_status')
        return status not in ['Power off', 'Low power', 'Full power', 'X-rays off']

    def set_power(self, state: str):
        if not self.get_variable('xrays'):
            raise ValueError('Cannot set state to {}: X-ray generator is off.'.format(state))
        state = str(state)
        if state.upper() in ['OFF', 'DOWN', 'POWER OFF', 'POWEROFF']:
            self.execute_command('poweroff')
        elif self.is_busy():
            raise ValueError('Cannot set state to {}: X-ray generator is busy.'.format(state))
        elif state.upper() in ['STANDBY', 'LOW']:
            if not self.is_warmup_needed():
                self.execute_command('standby')
            else:
                raise DeviceError('Warmup needed before powering up X-ray tube')
        elif state.upper() in ['HIGH', 'UP', 'FULL']:
            if not self.is_warmup_needed():
                self.execute_command('full_power')
            else:
                raise DeviceError('Warmup needed before powering up X-ray tube')
        else:
            raise ValueError(state)

    def get_power(self) -> str:
        if self.get_variable('_status') in ['Power off', 'X-rays off']:
            return 'off'
        elif self.get_variable('_status') in ['Low power']:
            return 'low'
        elif self.get_variable('_status') in ['Full power']:
            return 'full'
        else:
            return 'inconsistent'

    def load_state(self, dictionary):
        super().load_state(dictionary)
        self.last_powered = dictionary['last_powered']
        self.last_warmup = dictionary['last_warmup']
        self.warmup_interval = dictionary['warmup_interval']

    def save_state(self):
        dic = super().save_state()
        dic['last_powered'] = self.last_powered
        dic['last_warmup'] = self.last_warmup
        dic['warmup_interval'] = self.warmup_interval
        return dic

    def do_variable_change(self, varname: str, newvalue: object):
        if varname == 'power' and newvalue >= 9:
            self.last_powered = time.time()
        try:
            if self.get_variable('power') >= 9:
                self.last_powered = time.time()
        except KeyError:
            pass
        if varname == 'warmingup' and newvalue == False and self.get_variable('_status') == 'Warming up':
            # the warm-up process has just ended.
            if not self._warmup_stop_forced:
                self.last_warmup = time.time()
                self.execute_command('standby')

    def is_warmup_needed(self):
        """Warm-up is needed if both of the two criteria are met:

        - the time elapsed after the last warmup is more than self.warmup_interval
        - the time elapsed after the last powered-up state (i.e. when the power was >= 9W)
            is larger than self.warmup_interval"""
        return (((time.time() - self.last_powered) > self.warmup_interval) and
                ((time.time() - self.last_warmup) > self.warmup_interval))

    def start_warmup(self):
        self.execute_command('start_warmup')
        self._warmup_stop_forced = False

    def stop_warmup(self):
        self._warmup_stop_forced = True
        self.execute_command('stop_warmup')

    def can_open_shutter(self):
        return self.get_variable('interlock') and self.get_variable('xrays')
