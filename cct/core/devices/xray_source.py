import logging

from .device import Device_ModbusTCP

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class GeniX(Device_ModbusTCP):
    log_formatstr = '{_status}\t{ht}\t{current}\t{shutter}'

    def __init__(self, *args, **kwargs):
        self._logger = logger
        Device_ModbusTCP.__init__(self, *args, **kwargs)
        self.backend_interval = 0.4

    def _query_variable(self, variablename):
        if variablename is None:
            variablenames = ['ht', 'current', 'tubetime', 'shutter']
        else:
            variablenames = [variablename]
        if '_status' in variablenames:
            variablenames.append('power')
        if 'power' in variablenames:
            variablenames.extend(['ht', 'current'])
            while 'power' in variablenames:
                variablenames.remove('power')

        for vn in set(variablenames):
            if vn == 'ht':
                ht = self._read_integer(50) / 100
                self._update_variable('ht', ht)
                if 'current' in self._properties:
                    self._update_variable(
                        'power', ht * self._properties['current'])
            elif vn == 'current':
                current = self._read_integer(51) / 100
                self._update_variable('current', current)
                if 'ht' in self._properties:
                    self._update_variable(
                        'power', self._properties['ht'] * current)
            elif vn == 'tubetime':
                self._update_variable(
                    'tubetime', (self._read_integer(55) / 60.0 + self._read_integer(56)))
            elif vn in ['shutter', 'remote_mode', 'xrays', 'conditions_auto',
                        'tube_power', 'faults', 'xray_light_fault',
                        'shutter_light_fault', 'sensor2_fault',
                        'tube_position_fault', 'vacuum_fault',
                        'waterflow_fault', 'safety_shutter_fault',
                        'temperature_fault', 'sensor1_fault',
                        'relay_interlock_fault', 'door_fault',
                        'filament_fault', 'tube_warmup_needed',
                        'interlock', 'overridden', '_status']:
                statusbits = self._read_coils(210, 36)
                self._update_variable('remote_mode', statusbits[0])
                self._update_variable('xrays', statusbits[1])
                if not statusbits[1]:
                    self._update_variable('_status', 'X-rays off')
                if statusbits[2]:
                    self._update_variable('_status', 'Going to stand-by')
                if statusbits[3]:
                    self._update_variable('_status', 'Ramping up')
                self._update_variable('conditions_auto', statusbits[4])
                if statusbits[5]:
                    self._update_variable('_status', 'Powering down')
                if statusbits[6]:
                    self._update_variable('_status', 'Warming up')
                self._update_variable('tube_power', [30, 50][statusbits[7]])
                # statusbits[8] is unknown
                self._update_variable('faults', statusbits[9])
                self._update_variable('xray_light_fault', statusbits[10])
                self._update_variable('shutter_light_fault', statusbits[11])
                self._update_variable('sensor2_fault', statusbits[12])
                self._update_variable('tube_position_fault', statusbits[13])
                self._update_variable('vacuum_fault', statusbits[14])
                self._update_variable('waterflow_fault', statusbits[15])
                self._update_variable('safety_shutter_fault', statusbits[16])
                self._update_variable('temperature_fault', statusbits[17])
                self._update_variable('sensor1_fault', statusbits[18])
                self._update_variable('relay_interlock_fault', statusbits[19])
                self._update_variable('door_fault', statusbits[20])
                self._update_variable('filament_fault', statusbits[21])
                self._update_variable('tube_warmup_needed', statusbits[22])
                # statusbits[23] is unknown
                # statusbits[24] is just an 1Hz pulse signal
                self._update_variable('interlock', statusbits[25])
                if statusbits[26] and not statusbits[27]:
                    self._update_variable('shutter', False)
                elif statusbits[27] and not statusbits[26]:
                    self._update_variable('shutter', True)
                else:
                    # do nothing, we are in an intermediate state between open and
                    # closed, i.e. the shutter is just opening or closing.
                    pass
                # statusbits[28] is unknown
                self._update_variable('overridden', statusbits[29])
            else:
                raise NotImplementedError(vn)

            if ('power' in self._properties) and ('ht' in self._properties) and ('current' in self._properties):
                if self._properties['ht'] == 0 and self._properties['current'] == 0 and self._read_coils(211, 1)[0] == 1:
                    self._update_variable('_status', 'Power off')
                elif self._properties['power'] == 9:
                    self._update_variable('_status', 'Low power')
                elif self._properties['power'] == 30:
                    self._update_variable('_status', 'Full power')

    def _execute_command(self, commandname, arguments):
        if commandname == 'shutter':
            self._write_coil(247 + int(not arguments[0]), True)
            self._write_coil(247 + int(not arguments[0]), False)
        elif commandname == 'poweroff':
            self._write_coil(250, False)
            self._write_coil(244, True)
            self._write_coil(244, False)
        elif commandname == 'xrays':
            self._write_coil(251, arguments[0])
        elif commandname == 'reset_faults':
            self._write_coil(249, True)
            self._write_coil(249, False)
        elif commandname == 'start_warmup':
            self._write_coil(250, False)
            self._write_coil(245, True)
            self._write_coil(245, False)
        elif commandname == 'stop_warmup':
            self._write_coil(250, False)
            self._write_coil(246, True)
            self._write_coil(246, False)
        elif commandname == 'standby':
            self._write_coil(250, True)
        elif commandname == 'full_power':
            self._write_coil(250, False)
            self._write_coil(252, True)
            self._write_coil(252, False)
        else:
            raise NotImplementedError(commandname)
        self._queue_to_backend.put_nowait(('query', None, False))

    def shutter(self, requested_status):
        self.execute_command('shutter', requested_status)

    def reset_faults(self):
        """Try to reset faults."""
        self.execute_command('reset_faults')
