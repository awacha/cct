import struct
import multiprocessing
import queue
import logging
import os
import re
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from .device import Device_TCP, DeviceError

RE_FLOAT = r"[+-]?(\d+)*\.?\d+([eE][+-]?\d+)?"


class TMCMConversionError(DeviceError):
    pass


class TMCMcard(Device_TCP):

    def __init__(self, *args, **kwargs):
        Device_TCP.__init__(self, *args, **kwargs)
        self._clock_frequency = 16000000  # Hz
        # full step is 1.8° and one complete rotation is 1 mm. Thus one full
        # step is 1/200 mm.
        self._full_step_size = 1 / 200.
        self.backend_interval = 0.1
        self._sendqueue = multiprocessing.Queue()  # holds postponed sends.
        self._moving = None  # which motor is currently moving
        self._movinglock = multiprocessing.Lock()
        self._positions_loaded=multiprocessing.Event() # used for a boolean variable, nothing more
        self._load_positions()

    def _has_all_variables(self):
        variablenames = [base + '$' + str(motidx) for base in ['pulsedivisor',
                                                               'rampdivisor', 'microstepresolution',
                                                               'targetpositionreached', 'maxcurrent', 'standbycurrent',
                                                               'rightswitchstatus', 'leftswitchstatus', 'rightswitchenable',
                                                               'leftswitchenable', 'rampmode', 'freewheelingdelay', 'load', 'drivererror',
                                                               'targetposition', 'actualposition',
                                                               'actualspeed', 'targetspeed', 'maxspeed',
                                                               'maxacceleration',
                                                               'actualacceleration'] for motidx in self._motor_indices] + ['firmwareversion']
        return all([v in self._properties for v in variablenames])

    def _query_variable(self, variablename):
        if variablename is None:
            variablenames = [base + '$' + str(motidx) for base in ['pulsedivisor',
                                                                   'rampdivisor', 'microstepresolution',
                                                                   'targetpositionreached', 'maxcurrent', 'standbycurrent',
                                                                   'rightswitchstatus', 'leftswitchstatus', 'rightswitchenable',
                                                                   'leftswitchenable', 'rampmode', 'freewheelingdelay', 'load', 'drivererror',
                                                                   'targetposition', 'actualposition',
                                                                   'actualspeed', 'targetspeed', 'maxspeed',
                                                                   'maxacceleration',
                                                                   'actualacceleration'] for motidx in self._motor_indices] + ['firmwareversion']
            mustrefresh = ['targetpositionreached', 'targetposition', 'actualposition', 'actualspeed', 'targetspeed',
                           'rightswitchstatus', 'leftswitchstatus', 'actualacceleration', 'load', 'drivererror']
            variablenames = [vn for vn in variablenames
                             if (vn not in self._properties) or
                             any([vn.startswith(x) for x in mustrefresh])]
            for vn in variablenames:
                self._queue_to_backend.put_nowait(('query', vn, False))
            return
#        logger.debug('Motor controller %s: querying variable %s' %
#                     (self._instancename, variablename))
        try:
            motor_or_bank = int(variablename.split('$')[1])
            if motor_or_bank < 0 or motor_or_bank >= self._motorcount:
                raise DeviceError(
                    'Invalid motor/bank number', motor_or_bank)
        except (IndexError, ValueError):
            motor_or_bank = None
        if variablename == 'firmwareversion':
            self._send(
                self._construct_tmcl_command(136, 1, 0, 0))
        elif variablename.startswith('targetposition$'):
            self._send(
                self._construct_tmcl_command(6, 0, motor_or_bank, 0))
        elif variablename.startswith('actualposition$'):
            self._send(
                self._construct_tmcl_command(6, 1, motor_or_bank, 0))
        elif variablename.startswith('targetspeed$'):
            self._send(
                self._construct_tmcl_command(6, 2, motor_or_bank, 0))
        elif variablename.startswith('actualspeed$'):
            self._send(
                self._construct_tmcl_command(6, 3, motor_or_bank, 0))
        elif variablename.startswith('maxspeed$'):
            self._send(
                self._construct_tmcl_command(6, 4, motor_or_bank, 0))
        elif variablename.startswith('maxacceleration$'):
            self._send(
                self._construct_tmcl_command(6, 5, motor_or_bank, 0))
        elif variablename.startswith('maxcurrent$'):
            self._send(
                self._construct_tmcl_command(6, 6, motor_or_bank, 0))
        elif variablename.startswith('standbycurrent$'):
            self._send(
                self._construct_tmcl_command(6, 7, motor_or_bank, 0))
        elif variablename.startswith('targetpositionreached$'):
            self._send(
                self._construct_tmcl_command(6, 8, motor_or_bank, 0))
        elif variablename.startswith('rightswitchstatus$'):
            self._send(
                self._construct_tmcl_command(6, 10, motor_or_bank, 0))
        elif variablename.startswith('leftswitchstatus$'):
            self._send(
                self._construct_tmcl_command(6, 11, motor_or_bank, 0))
        elif variablename.startswith('rightswitchenable$'):
            self._send(
                self._construct_tmcl_command(6, 12, motor_or_bank, 0))
        elif variablename.startswith('leftswitchenable$'):
            self._send(
                self._construct_tmcl_command(6, 13, motor_or_bank, 0))
        elif variablename.startswith('actualacceleration$'):
            self._send(
                self._construct_tmcl_command(6, 135, motor_or_bank, 0))
        elif variablename.startswith('rampmode$'):
            self._send(
                self._construct_tmcl_command(6, 138, motor_or_bank, 0))
        elif variablename.startswith('microstepresolution$'):
            self._send(
                self._construct_tmcl_command(6, 140, motor_or_bank, 0))
        elif variablename.startswith('rampdivisor$'):
            self._send(
                self._construct_tmcl_command(6, 153, motor_or_bank, 0))
        elif variablename.startswith('pulsedivisor$'):
            self._send(
                self._construct_tmcl_command(6, 154, motor_or_bank, 0))
        elif variablename.startswith('freewheelingdelay$'):
            self._send(
                self._construct_tmcl_command(6, 204, motor_or_bank, 0))
        elif variablename.startswith('load$'):
            self._send(
                self._construct_tmcl_command(6, 206, motor_or_bank, 0))
        elif variablename.startswith('drivererror$'):
            self._send(
                self._construct_tmcl_command(6, 208, motor_or_bank, 0))
        else:
            raise NotImplementedError(variablename)

    def _process_incoming_message(self, message):
        if not hasattr(self, '_lastsent'):
            raise DeviceError(
                'Asynchronous message received from motor controller')
        try:
            if len(message) != 9:
                raise DeviceError(
                    'Invalid message (length must be 9): ' + str(message))
            if (sum(message[:-1]) % 256) != message[-1]:
                raise DeviceError(
                    'Invalid message (checksum error): ' + str(message))
            status = message[2]
            cmdnum = message[3]
            value = struct.unpack('>i', message[4:8])[0]
            if status == 1:
                raise DeviceError(
                    'TMCL error: wrong checksum in message: ' + str(message))
            elif status == 2:
                raise DeviceError(
                    'TMCL error: invalid command in message: ' + str(message))
            elif status == 3:
                raise DeviceError(
                    'TMCL error: wrong type in message: ' + str(message))
            elif status == 4:
                raise DeviceError(
                    'TMCL error: invalid value in message: ' + str(message))
            elif status == 5:
                raise DeviceError(
                    'TMCL error: configuration EEPROM locked in message: ' + str(message))
            elif status == 6:
                raise DeviceError(
                    'TMCL error: command not available in message: ' + str(message))
            elif status != 100:
                raise DeviceError(
                    'TMCL error: unspecified error in message: ' + str(message))
            if cmdnum == 6:  # get axis parameter
                typenum = self._lastsent[2]
                motor_or_bank = str(self._lastsent[3])
                motoridx = self._lastsent[3]
                if typenum == 0:
                    self._update_variable(
                        'targetposition$' + motor_or_bank, self._convert_pos_to_phys(value, motoridx))
                elif typenum == 1:
                    self._update_variable(
                        'actualposition$' + motor_or_bank, self._convert_pos_to_phys(value, motoridx))
                    try:
                        if self._properties['actualspeed$'+motor_or_bank]==0:
                            self._save_positions()
                    except KeyError:
                        # actualspeed for this motor not yet measured
                        logger.debug('actualposition changed for motor %s on controller %s, but actualspeed not yet available: not saving positions'%(motor_or_bank, self._instancename))
                elif typenum == 2:
                    self._update_variable(
                        'targetspeed$' + motor_or_bank, self._convert_speed_to_phys(value, motoridx))
                elif typenum == 3:
                    if self._update_variable(
                            'actualspeed$' + motor_or_bank, self._convert_speed_to_phys(value, motoridx)) and value == 0:
                        # the current motor has just stopped
                        self._motor_indices = list(range(self._motorcount))
                        with self._movinglock:
                            self._moving = None
                        self._update_variable('_status', 'idle')
                        self._update_variable('_status$%d' % motoridx, 'idle')
                        self._save_positions()
                elif typenum == 4:
                    self._update_variable(
                        'maxspeed$' + motor_or_bank, self._convert_speed_to_phys(value, motoridx))
                elif typenum == 5:
                    self._update_variable(
                        'maxacceleration$' + motor_or_bank, self._convert_accel_to_phys(value, motoridx))
                elif typenum == 6:
                    self._update_variable(
                        'maxcurrent$' + motor_or_bank, self._convert_current_to_phys(value, motoridx))
                elif typenum == 7:
                    self._update_variable(
                        'standbycurrent$' + motor_or_bank, self._convert_current_to_phys(value, motoridx))
                elif typenum == 8:
                    self._update_variable(
                        'targetpositionreached$' + motor_or_bank, bool(value))
                elif typenum == 10:
                    self._update_variable(
                        'rightswitchstatus$' + motor_or_bank, bool(value))
                elif typenum == 11:
                    self._update_variable(
                        'leftswitchstatus$' + motor_or_bank, bool(value))
                elif typenum == 12:
                    self._update_variable(
                        'rightswitchenable$' + motor_or_bank, not bool(value))
                elif typenum == 13:
                    self._update_variable(
                        'leftswitchenable$' + motor_or_bank, not bool(value))
                elif typenum == 135:
                    self._update_variable(
                        'actualacceleration$' + motor_or_bank, self._convert_accel_to_phys(value, motoridx))
                elif typenum == 138:
                    self._update_variable('rampmode$' + motor_or_bank, value)
                elif typenum == 140:
                    self._update_variable(
                        'microstepresolution$' + motor_or_bank, value)
                elif typenum == 154:
                    self._update_variable(
                        'pulsedivisor$' + motor_or_bank, value)
                elif typenum == 153:
                    self._update_variable(
                        'rampdivisor$' + motor_or_bank, value)
                elif typenum == 204:
                    self._update_variable(
                        'freewheelingdelay$' + motor_or_bank, value / 1000)
                elif typenum == 206:
                    self._update_variable('load$' + motor_or_bank, value)
                elif typenum == 208:
                    self._update_variable(
                        'drivererror$' + motor_or_bank, value)
                else:
                    raise NotImplementedError(typenum)
            elif cmdnum == 136:
                self._update_variable('firmwareversion', 'TMCM%d' % (
                    value // 0x10000) + ', firmware v%d.%d' % ((value % 0x10000) / 0x100, value % 0x100))
        finally:
            try:
                msg = self._sendqueue.get_nowait()
                self._lastsent = msg
                Device_TCP._send(self, msg)
            except queue.Empty:
                del self._lastsent

    def _send(self, message):
        if hasattr(self, '_lastsent'):
            self._sendqueue.put_nowait(message)
            return
        self._lastsent = message
        Device_TCP._send(self, message)

    def _convert_pos_to_phys(self, pos, motoridx):
        """Convert the raw value of position to physical dimensions.

        pos is in microsteps. The number of microsteps in a full step is 2**microstepresolution"""
        try:
            return pos / 2**self._properties['microstepresolution$%d' % motoridx] * self._full_step_size
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_pos_to_raw(self, pos, motoridx):
        """Convert the raw value of position to physical dimensions.

        pos is in microsteps. The number of microsteps in a full step is 2**microstepresolution"""
        try:
            return pos * 2**self._properties['microstepresolution$%d' % motoridx] / self._full_step_size
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_speed_to_phys(self, speed, motoridx):
        try:
            return speed / 2**(self._properties['pulsedivisor$%d' % motoridx] + self._properties['microstepresolution$%d' % motoridx] + 16) * self._clock_frequency * self._full_step_size
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_speed_to_raw(self, speed, motoridx):
        try:
            return int(speed * 2**(self._properties['pulsedivisor$%d' % motoridx] + self._properties['microstepresolution$%d' % motoridx] + 16) / self._clock_frequency / self._full_step_size)
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_accel_to_phys(self, accel, motoridx):
        try:
            return accel * self._full_step_size * self._clock_frequency**2 / 2**(self._properties['pulsedivisor$%d' % motoridx] + self._properties['rampdivisor$%d' % motoridx] + self._properties['microstepresolution$%d' % motoridx] + 29)
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_accel_to_raw(self, accel, motoridx):
        try:
            return int(accel / self._full_step_size / self._clock_frequency**2 * 2**(self._properties['pulsedivisor$%d' % motoridx] + self._properties['rampdivisor$%d' % motoridx] + self._properties['microstepresolution$%d' % motoridx] + 29))
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_current_to_phys(self, current, motoridx):
        try:
            return current * self._top_rms_current / 255
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_current_to_raw(self, current, motoridx):
        try:
            return int(current * 255 / self._top_rms_currnet)
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _construct_tmcl_command(self, cmdnum, typenum, motor_or_bank, value):
        cmd = bytes([1, cmdnum, typenum, motor_or_bank]) + \
            struct.pack('>i', int(value))
        return cmd + bytes([sum(cmd) % 256])

    def moveto(self, motor, pos):
        if not self._positions_loaded.is_set():
            raise DeviceError('Cannot move motors until positions and soft limits have been loaded')
        limits = (self._convert_pos_to_raw(self._properties['softleft$%d'%motor], motor),
                  self._convert_pos_to_raw(self._properties['softright$%d'%motor], motor))
        posraw = self._convert_pos_to_raw(pos, motor)
        self._queue_to_backend.put_nowait(
            ('execute', 'moveto', (motor, posraw, limits)))

    def moverel(self, motor, pos):
        if not self._positions_loaded.is_set():
            raise DeviceError('Cannot move motors until positions and soft limits have been loaded')
        limits = (self._convert_pos_to_raw(self._properties['softleft$%d'%motor], motor),
                  self._convert_pos_to_raw(self._properties['softright$%d'%motor], motor))
        posraw = self._convert_pos_to_raw(pos, motor)
        self._queue_to_backend.put_nowait(
            ('execute', 'moverel', (motor, posraw, limits)))

    def stop(self, motor):
        self._queue_to_backend.put_nowait(('execute', 'stop', motor))

    def calibrate(self, motor, pos):
        if not self.checklimits(motor, pos):
            raise DeviceError('Cannot calibrate outside soft limits')
        self.set_variable('rampmode$%d' % motor, 2)
        self.set_variable('actualposition$%d' % motor, pos)
        self.set_variable('targetposition$%d' % motor, pos)

    def where(self, motor):
        return self.get_variable('actualposition$%d' % motor)

    def _save_state(self):
        dic = Device_TCP._save_state(self)
#        dic['softlimits'] = self._softlimits
        return dic

    def _execute_command(self, commandname, arguments):
        if commandname == 'moveto':
            with self._movinglock:
                motor, pos, limits = arguments
                if self._moving is not None:
                    raise DeviceError(
                        'Cannot move motor %d: another motor (%d) is currently moving' % (motor, self._moving))
                if limits is not None:
                    if pos < limits[0] or pos > limits[1]:
                        raise DeviceError(
                            'Cannot move motor %d, requested position outside soft limits' % motor)
                if self._convert_pos_to_raw(self._properties['actualposition$%d' % motor], motor) == pos:
                    self._update_variable('_status', 'idle', force=True)
                    self._update_variable(
                        '_status$%d' % motor, 'idle', force=True)
                else:
                    self._motor_indices = [motor]
                    self._moving = motor
                    self._update_variable('_status', 'Moving #%d' % motor)
                    self._update_variable('_status$%d' % motor, 'Moving')
                    self._send(self._construct_tmcl_command(4, 0, motor, pos))
                    self.refresh_variable('actualspeed$%d'%motor)
        elif commandname == 'moverel':
            with self._movinglock:
                motor, pos, limits = arguments
                if self._moving is not None:
                    raise DeviceError(
                        'Cannot move motor %d: another motor (%d) is currently moving' % (motor, self._moving))
                if limits is not None:
                    where = self._convert_pos_to_raw(
                        self._properties['actualposition$%d' % motor], motor)
                    if pos + where < limits[0] or pos + where > limits[1]:
                        raise DeviceError(
                            'Cannot move motor %d, requested position outside soft limits' % motor)
                if pos == 0:
                    self._update_variable('_status', 'idle', force=True)
                    self._update_variable(
                        '_status$%d' % motor, 'idle', force=True)
                else:
                    self._motor_indices = [motor]
                    self._moving = motor
                    self._update_variable('_status', 'Moving #%d' % motor)
                    self._update_variable('_status$%d' % motor, 'Moving')
                    self._send(self._construct_tmcl_command(4, 1, motor, pos))
                    self.refresh_variable('actualspeed$%d'%motor)
        elif commandname == 'stop':
            motor = arguments
            self._motor_indices = [motor]
            self._send(self._construct_tmcl_command(3, 0, motor, 0))
        else:
            raise NotImplementedError(commandname)

    def _set_variable(self, variable, value):
        try:
            motor_or_bank = int(variable.split('$')[1])
            if motor_or_bank < 0 or motor_or_bank >= self._motorcount:
                raise DeviceError(
                    'Invalid motor/bank number', motor_or_bank)
        except (IndexError, ValueError):
            motor_or_bank = None
        try:
            if variable.startswith('targetposition$'):
                self._send(
                    self._construct_tmcl_command(5, 0, motor_or_bank, self._convert_pos_to_raw(value, motor_or_bank)))
            elif variable.startswith('actualposition$'):
                self._send(
                    self._construct_tmcl_command(5, 1, motor_or_bank, self._convert_pos_to_raw(value, motor_or_bank)))
            elif variable.startswith('targetspeed$'):
                self._send(
                    self._construct_tmcl_command(5, 2, motor_or_bank, self._convert_speed_to_raw(value, motor_or_bank)))
            elif variable.startswith('actualspeed$'):
                self._send(
                    self._construct_tmcl_command(5, 3, motor_or_bank, self._convert_speed_to_raw(value, motor_or_bank)))
            elif variable.startswith('maxspeed$'):
                self._send(
                    self._construct_tmcl_command(5, 4, motor_or_bank, self._convert_speed_to_raw(value, motor_or_bank)))
                self._send(
                    self._construct_tmcl_command(7, 4, motor_or_bank, 0))
            elif variable.startswith('maxacceleration$'):
                self._send(
                    self._construct_tmcl_command(5, 5, motor_or_bank, self._convert_accel_to_raw(value, motor_or_bank)))
                self._send(
                    self._construct_tmcl_command(7, 5, motor_or_bank, 0))
            elif variable.startswith('maxcurrent$'):
                self._send(
                    self._construct_tmcl_command(5, 6, motor_or_bank, self._convert_current_to_raw(value, motor_or_bank)))
            elif variable.startswith('standbycurrent$'):
                self._send(
                    self._construct_tmcl_command(5, 7, motor_or_bank, self._convert_current_to_raw(value, motor_or_bank)))
            elif variable.startswith('rightswitchenable$'):
                self._send(
                    self._construct_tmcl_command(5, 12, motor_or_bank, not bool(value)))
                self._send(
                    self._construct_tmcl_command(7, 12, motor_or_bank, 0))
            elif variable.startswith('leftswitchenable$'):
                self._send(
                    self._construct_tmcl_command(5, 13, motor_or_bank, not bool(value)))
                self._send(
                    self._construct_tmcl_command(7, 13, motor_or_bank, 0))
            elif variable.startswith('rampmode$'):
                if value not in [0, 1, 2]:
                    raise ValueError('Invalid ramp mode: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 138, motor_or_bank, value))
            elif variable.startswith('microstepresolution$'):
                if value < 0 or value > self._max_microsteps:
                    raise ValueError(
                        'Invalid microstep resolution: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 140, motor_or_bank, value))
                self._send(
                    self._construct_tmcl_command(7, 140, motor_or_bank, 0))
            elif variable.startswith('rampdivisor$'):
                if value < 0 or value > 13:
                    raise ValueError('Invalid ramp divisor: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 153, motor_or_bank, value))
                self._send(
                    self._construct_tmcl_command(7, 153, motor_or_bank, 0))
            elif variable.startswith('pulsedivisor$'):
                if value < 0 or value > 13:
                    raise ValueError('Invalid pulse divisor: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 154, motor_or_bank, value))
                self._send(
                    self._construct_tmcl_command(7, 154, motor_or_bank, 0))
            elif variable.startswith('freewheelingdelay$'):
                if value < 0 or value > 65.535:
                    raise ValueError('Invalid freewheeling delay: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 204, motor_or_bank, value * 1000))
                self._send(
                    self._construct_tmcl_command(7, 204, motor_or_bank, 0))
            else:
                raise NotImplementedError(variable)
        except TMCMConversionError:
            self._queue_to_backend.put_nowait(('set', variable, value))

    def _save_positions(self):
        with self._movinglock:
            if not self._positions_loaded.is_set():
                # avoid overwriting the position file before it can be loaded.
                logger.debug('Not saving positions yet: file exists and up to now no complete loading happened.')
                return
            with open(os.path.join(self.configdir, self._instancename + '.motorpos'), 'wt', encoding='utf-8') as f:
                for mot in range(self._motorcount):
                    f.write('%d: %g (%g, %g)\n' % (
                        mot, self.where(mot), self._properties['softleft$%d'%mot], self._properties['softright$%d'%mot]))

    def _load_positions(self):
        with self._movinglock:
            if self._moving:
                raise DeviceError(
                    'Cannot load positions from file if motor is moving!')
            try:
                with open(os.path.join(self.configdir, self._instancename + '.motorpos'), 'rt', encoding='utf-8') as f:
                    for l in f:
                        m = re.match('(?P<motoridx>\d+): (?P<position>' + RE_FLOAT +
                                     ') \((?P<leftlim>' + RE_FLOAT + '), (?P<rightlim>' + RE_FLOAT + ')\)', l)
                        if not m:
                            raise DeviceError(
                                'Invalid line in motor position file: ' + l)
                        gd = m.groupdict()
                        idx = int(gd['motoridx'])
                        self._properties['softleft$%d'%idx]=float(gd['leftlim'])
                        self._properties['softright$%d'%idx]=float(gd['rightlim'])
                        if 'actualposition$%d'%idx not in self._properties:
                            continue
                        else:
                            if abs(self._properties['actualposition$%d'%idx] - float(gd['position']))>0.001:
                                logger.warning('Current position (%.3f) of motor %d on controller %s differs from the stored one (%.3f): calibrating to the stored value.'%(
                                    self._properties['actualposition$%d'%idx], idx, self._instancename, float(gd['position'])))
                                self.calibrate(idx, float(gd['position']))
                            self._positions_loaded.set()
            except FileNotFoundError:
                self._positions_loaded.set()

    def _initialize_after_connect(self):
        Device_TCP._initialize_after_connect(self)
        self.refresh_variable('firmwareversion', check_backend_alive=False)

    def moving(self):
        with self._movinglock:
            return self._moving

    def do_startupdone(self):
        logger.debug('Loading positions for controller %s' %
                     self._instancename)
        self._load_positions()
        Device_TCP.do_startupdone(self)

    def checklimits(self, motor, position):
        return (position >= self._properties['softleft$%d'%motor]) and (position <= self._properties['softright$%d'%motor])

    def set_limits(self, index, left=None, right=None):
        if left is not None:
            self._properties['softleft$%d'%index]=left
            self.emit('variable-change','softleft$%d'%index,left)
        if right is not None:
            self._properties['softright$%d'%index]=right
            self.emit('variable-change', 'softright$%d'%index, right)

    def get_limits(self, index):
        return self._properties['softleft$%d'%index], self._properties['softright$%d'%index]

    def set_variable(self, name, value):
        if name.startswith('softleft$') or name.startswith('softright$'):
            if self._properties[name]!=value:
                self._properties[name]=value
                self._save_positions()
                self.emit('variable-change', name, value)
        else:
            return Device_TCP.set_variable(self,name, value)

class TMCM351(TMCMcard):

    def __init__(self, *args, **kwargs):
        TMCMcard.__init__(self, *args, **kwargs)
        self._top_rms_current = 2.8
        self._motorcount = 3
        self._motor_indices = [0, 1, 2]
        self._max_microsteps = 6
        for i in range(self._motorcount):
            self._properties['softleft$%d'%i]=-100
            self._properties['softright$%d'%i]=100

    def decode_error_flags(self, flags):
        lis=[]
        if flags&0b1:
            lis.append('Overcurrent bridge A low side')
        if flags&0b10:
            lis.append('Overcurrent bridge B low side')
        if flags&0b100:
            lis.append('Open load bridge A')
        if flags&0b1000:
            lis.append('Open load bridge B')
        if flags&0b10000:
            lis.append('Overcurrent high side')
        if flags&0b100000:
            lis.append('Driver undervoltage')
        if flags&0b1000000:
            lis.append('Temperature warning')
        if flags&0b10000000:
            lis.append('Overtemperature')
        return lis


class TMCM6110(TMCMcard):

    def __init__(self, *args, **kwargs):
        TMCMcard.__init__(self, *args, **kwargs)
        self._top_rms_current = 1.1
        self._motorcount = 6
        self._motor_indices = [0, 1, 2, 3, 4, 5]
        self._max_microsteps = 8
        self._softlimits = [[-100, 100]] * self._motorcount
        for i in range(self._motorcount):
            self._properties['softleft$%d'%i]=-100
            self._properties['softright$%d'%i]=100

    def decode_error_flags(self, flags):
        lis=[]
        if flags&0b1:
            lis.append('stallGuard2 threshold reached')
        if flags&0b10:
            lis.append('Overtemperature')
        if flags&0b100:
            lis.append('Pre-warning overtemperature')
        if flags&0b1000:
            lis.append('Short to ground A')
        if flags&0b10000:
            lis.append('Short to ground B')
        if flags&0b100000:
            lis.append('Open load A')
        if flags&0b1000000:
            lis.append('Open load B')
        if flags&0b10000000:
            lis.append('Stand still')
        return lis