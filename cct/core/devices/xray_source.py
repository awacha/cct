import logging
import time

from .device import Device_ModbusTCP, UnknownVariable, UnknownCommand

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class GeniX(Device_ModbusTCP):
    log_formatstr = '{_status}\t{ht}\t{current}\t{shutter}'

    _all_variables = ['ht', 'current', 'tubetime', 'shutter', 'power', 'remote_mode', 'xrays', 'conditions_auto',
                              'tube_power', 'faults', 'xray_light_fault',
                              'shutter_light_fault', 'sensor2_fault',
                              'tube_position_fault', 'vacuum_fault',
                              'waterflow_fault', 'safety_shutter_fault',
                              'temperature_fault', 'sensor1_fault',
                              'relay_interlock_fault', 'door_fault',
                              'filament_fault', 'tube_warmup_needed',
                              'interlock', 'overridden']

    _minimum_query_variables = ['ht', 'current', 'tubetime', 'shutter']

    _interlock_fixing_time = 3 # time to ascertain if the interlock is really OK.

    backend_interval = 0.3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loglevel = logger.level

    def _query_variable(self, variablename, minimum_query_variables=None):

        if not super()._query_variable(variablename):
            return False

        if variablename == 'power':
            pass
        elif variablename == 'ht':
            ht = self._read_integer(50) / 100
            if self._update_variable('ht', ht):
                try:
                    power = self._properties['ht']* self._properties['current']
                    self._update_variable('power',power)
                    self._update_variable('_auxstatus', '{0[ht]:.2f} kV {0[current]:.2f} mA'.format(
                        self._properties))
                except KeyError:
                    pass
        elif variablename=='current':
            current = self._read_integer(51) / 100
            if self._update_variable('current', current):
                try:
                    power = self._properties['ht'] * self._properties['current']
                    self._update_variable('power', power)
                    self._update_variable('_auxstatus', '{0[ht]:.2f} kV 0[current]:.2f} mA'.format(
                        self._properties))
                except KeyError:
                    pass
        elif variablename == 'tubetime':
            self._update_variable(
                'tubetime', (self._read_integer(55) / 60.0 + self._read_integer(56)))
        elif variablename in ['shutter', 'remote_mode', 'xrays', 'conditions_auto',
                              'tube_power', 'faults', 'xray_light_fault',
                              'shutter_light_fault', 'sensor2_fault',
                              'tube_position_fault', 'vacuum_fault',
                              'waterflow_fault', 'safety_shutter_fault',
                              'temperature_fault', 'sensor1_fault',
                              'relay_interlock_fault', 'door_fault',
                              'filament_fault', 'tube_warmup_needed',
                              'interlock', 'overridden', '_status']:
            statusbits = self._read_coils(210, 36)
            self._last_readstatus=time.monotonic()
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
            if self._update_variable('interlock_lowlevel',statusbits[25]):
                self._interlock_lastchange=time.monotonic()
            if statusbits[25]:
                if time.monotonic()-self._interlock_lastchange>self._interlock_fixing_time:
                    # if a given amount of time has elapsed since we have
                    # last seen an interlock broken state, this means that
                    # we are truly in interlock OK state.
                    self._update_variable('interlock',True)
                # otherwise do nothing.
            else:
                # if interlock_lowlevel signals Broken, set interlock to broken.
                self._update_variable('interlock',False)
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
            try:
                if statusbits[1]: # X-rays ON
                    if not (statusbits[2] or statusbits[3] or statusbits[5] or statusbits[6]):
                        # if not going to standby, not ramping up,
                        # not powering down and not warming up, decide the
                        # value of _status by the current output power
                        if (self._properties['ht']==0 and
                                    self._properties['current'] == 0):
                            self._update_variable('_status', 'Power off')
                        elif self._properties['power']==9:
                            self._update_variable('_status', 'Low power')
                        elif self._properties['power']==30:
                            self._update_variable('_status', 'Full power')
            except KeyError:
                pass
        else:
            raise UnknownVariable(variablename)

    def _execute_command(self, commandname, arguments):
        if commandname == 'shutter':
            self._write_coil(247 + int(not arguments[0]), True)
            self._write_coil(247 + int(not arguments[0]), False)
            time.sleep(1)
            self._query_variable('shutter')
        elif commandname == 'poweroff':
            self._write_coil(250, False) # Not standby
            # Pulse the power-off coil
            self._write_coil(244, True)
            self._write_coil(244, False)
        elif commandname == 'xrays':
            self._write_coil(251, bool(arguments[0]))
        elif commandname == 'reset_faults':
            # Pulse the reset_faults coil
            self._write_coil(249, True)
            self._write_coil(249, False)
        elif commandname == 'start_warmup':
            self._write_coil(250, False) # Not standby
            # Pulse the start warmup coil
            self._write_coil(245, True)
            self._write_coil(245, False)
        elif commandname == 'stop_warmup':
            self._write_coil(250, False) # Not standby
            # Pulse the stop warmup coil
            self._write_coil(246, True)
            self._write_coil(246, False)
        elif commandname == 'standby':
            self._write_coil(250, True) # Standby
        elif commandname == 'full_power':
            self._write_coil(250, False) # Not standby
            # Pulse the full-power coil
            self._write_coil(252, True)
            self._write_coil(252, False)
        else:
            raise UnknownCommand(commandname)

    def shutter(self, requested_status):
        "Open or close the shutter"
        self.execute_command('shutter', requested_status)

    def reset_faults(self):
        """Try to reset faults."""
        self.execute_command('reset_faults')

    def _get_telemetry(self):
        tm=super()._get_telemetry()
        if hasattr(self, '_last_readstatus'):
            tm['last_readstatus']=time.monotonic()-self._last_readstatus
        return tm