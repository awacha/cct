import itertools
import logging
import multiprocessing
import os
import re
import struct
import time

from .device import Device_TCP, DeviceError, UnknownCommand, UnknownVariable, ReadOnlyVariable

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


RE_FLOAT = r"[+-]?(\d+)*\.?\d+([eE][+-]?\d+)?"

# list of essential variables, which are due to change during motor movement.
# Other variables not listed here can safely be assumed as constant during
# most of the time. Those will only be checked when no motor is moving.
VOLATILE_VARIABLES = ['targetpositionreached', 'actualspeed',
                      'targetposition', 'actualposition', 'targetspeed',
                      'rightswitchstatus', 'leftswitchstatus',
                      'actualacceleration', 'load', 'drivererror', 'rampmode']

# These variables should be repeated for each motor. Practically this means
# that each TMCMcard will have several copies of these, distinguished by
# $<motorid> suffixes, such as pulsedivisor$0, pulsedivisor$1, etc.
PER_MOTOR_VARIABLES = ['pulsedivisor', 'rampdivisor', 'microstepresolution',
                       'targetpositionreached', 'maxcurrent', 'standbycurrent',
                       'rightswitchstatus', 'leftswitchstatus',
                       'rightswitchenable', 'leftswitchenable', 'rampmode',
                       'freewheelingdelay', 'load', 'drivererror',
                       'targetposition', 'actualposition', 'actualspeed',
                       'targetspeed', 'maxspeed', 'maxacceleration',
                       'actualacceleration']

DEVICE_VARIABLES = ['firmwareversion']


class TMCMConversionError(DeviceError):
    pass


class TMCMcard(Device_TCP):
    """Motor controller card from Trinamic GmbH, Hamburg, Germany. Developed for TMCM351 and TMCM6110, may or may not
    work for other models."""

    # number of motors supported by this card
    _N_axes = 0
    # top RMS coil current value (Amper)
    _top_RMS_current= 10000000
    # max value of microstepresolution
    _max_microsteps=6

    # internal clock frequency of the card, Hz
    _clock_frequency = 16000000 # 16 MHz
    # full step is 1.8° and one complete rotation is 1 mm. Thus one full
    # step is 1/200 mm.
    _full_step_size = 1 / 200.

    backend_interval = 0.1

    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)

        self._all_variables=DEVICE_VARIABLES+['%s$%d'%(vn,motidx)
                                              for vn, motidx in itertools.product(
                PER_MOTOR_VARIABLES, range(self._N_axes))]

        self._minimum_query_variables=self._all_variables[:]

        # self._moving: not present if no motor is moving. Otherwise a dict with the
        # following items: 'index': the index of the currently moving motor.
        # 'starttime': time of issuing the move command
        # 'startposition': RAW starting position
        # This dict belongs entirely to the backend process
        self._moving = None
        # if this flag is set, no movement is possible. This is inherited by the
        # backend process.
        self._busyflag = multiprocessing.BoundedSemaphore(1)
        # this flag signifies that the stored position file has been loaded
        # successfully, or did not exist when trying to load it. Until this
        # flag has been set, the position file cannot be overwritten.
        # Saving and loading motor positions (and soft limits) from the file
        # is only permitted from the backend. The frontend can only initiate
        # this via a well-crafted execute_command()
        self._positions_loaded = multiprocessing.Event()

    def _query_variable(self, variablename, minimum_query_variables=None):
        if variablename is None:
            if hasattr(self._moving):
                # if a motor is moving, only queue the essential variables
                variablenames = [vn + '$%d' % self._moving['index'] for vn in VOLATILE_VARIABLES]
            else:
                variablenames = []
                # if no motor is moving, query all volatile variables, i.e.
                # those which can change without user interaction.
                for motor in range(self._motorcount):
                    variablenames.extend([vn + '$%d' % motor for vn in VOLATILE_VARIABLES])
                # If there are not yet queried one apart from those already in
                # variablenames, query them as well
                missingvariables = [vn for vn in self._all_variables
                                    if ((vn not in self._properties) and
                                        (vn not in variablenames))]
                variablenames.extend(missingvariables)
            super()._query_variable(None, variablenames)
            return  # do no actual querying.
        try:
            motor_idx = int(variablename.split('$')[1])
            if motor_idx < 0 or motor_idx >= self._N_axes:
                raise DeviceError(
                    'Invalid motor index', motor_idx)
        except (IndexError, ValueError):
            motor_idx = None
        if variablename == 'firmwareversion':
            self._send(
                self._construct_tmcl_command(136, 1, 0, 0))
        elif (variablename.startswith('targetposition$') or
                  variablename.startswith('targetpositionraw$')):
            self._send(
                self._construct_tmcl_command(6, 0, motor_idx, 0))
        elif (variablename.startswith('actualposition$') or
                  variablename.startswith('actualpositionraw$')):
            self._send(
                self._construct_tmcl_command(6, 1, motor_idx, 0))
        elif variablename.startswith('targetspeed$'):
            self._send(
                self._construct_tmcl_command(6, 2, motor_idx, 0))
        elif variablename.startswith('actualspeed$'):
            self._send(
                self._construct_tmcl_command(6, 3, motor_idx, 0))
        elif variablename.startswith('maxspeed$'):
            self._send(
                self._construct_tmcl_command(6, 4, motor_idx, 0))
        elif variablename.startswith('maxacceleration$'):
            self._send(
                self._construct_tmcl_command(6, 5, motor_idx, 0))
        elif variablename.startswith('maxcurrent$'):
            self._send(
                self._construct_tmcl_command(6, 6, motor_idx, 0))
        elif variablename.startswith('standbycurrent$'):
            self._send(
                self._construct_tmcl_command(6, 7, motor_idx, 0))
        elif variablename.startswith('targetpositionreached$'):
            self._send(
                self._construct_tmcl_command(6, 8, motor_idx, 0))
        elif variablename.startswith('rightswitchstatus$'):
            self._send(
                self._construct_tmcl_command(6, 10, motor_idx, 0))
        elif variablename.startswith('leftswitchstatus$'):
            self._send(
                self._construct_tmcl_command(6, 11, motor_idx, 0))
        elif variablename.startswith('rightswitchenable$'):
            self._send(
                self._construct_tmcl_command(6, 12, motor_idx, 0))
        elif variablename.startswith('leftswitchenable$'):
            self._send(
                self._construct_tmcl_command(6, 13, motor_idx, 0))
        elif variablename.startswith('actualacceleration$'):
            self._send(
                self._construct_tmcl_command(6, 135, motor_idx, 0))
        elif variablename.startswith('rampmode$'):
            self._send(
                self._construct_tmcl_command(6, 138, motor_idx, 0))
        elif variablename.startswith('microstepresolution$'):
            self._send(
                self._construct_tmcl_command(6, 140, motor_idx, 0))
        elif variablename.startswith('rampdivisor$'):
            self._send(
                self._construct_tmcl_command(6, 153, motor_idx, 0))
        elif variablename.startswith('pulsedivisor$'):
            self._send(
                self._construct_tmcl_command(6, 154, motor_idx, 0))
        elif variablename.startswith('freewheelingdelay$'):
            self._send(
                self._construct_tmcl_command(6, 204, motor_idx, 0))
        elif variablename.startswith('load$'):
            self._send(
                self._construct_tmcl_command(6, 206, motor_idx, 0))
        elif variablename.startswith('drivererror$'):
            self._send(
                self._construct_tmcl_command(6, 208, motor_idx, 0))
        elif variablename.startswith('softleft$') or variablename.startswith('softright$'):
            # these are pseudo-(device variables)
            self._update_variable(variablename, self._properties[variablename], force=True)
        else:
            raise UnknownVariable(variablename)

    def _get_complete_messages(self, message):
        messages=[]
        while len(message)>=9:
            messages.append(message[:9])
            message=message[9:]
        # now add the remainder
        messages.append(message)
        return messages

    def _moving_idx(self):
        try:
            return self._moving['index']
        except AttributeError:
            return None

    def _process_incoming_message(self, message, original_sent=None):
        self._cleartosend_semaphore.release()
        if (sum(message[:-1]) % 256) != message[-1]:
            raise DeviceError(
                'Invalid message (checksum error): ' + str(message))
        status = message[2]
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

        cmdnum = message[3]
        value = struct.unpack('>i', message[4:8])[0]
        if cmdnum == 6:  # get axis parameter
            typenum = original_sent[2]
            motor_idx = str(original_sent[3])
            motoridx = original_sent[3]
            try:
                if typenum == 0:  # targetposition
                    self._update_variable(
                        'targetposition$' + motor_idx, self._convert_pos_to_phys(value, motoridx))
                    self._update_variable('targetpositionraw$' + motor_idx, value)
                elif typenum == 1:  # actualposition
                    newvalue = self._convert_pos_to_phys(value, motoridx)
                    self._update_variable('actualpositionraw$' + motor_idx, value)
                    if self._update_variable('actualposition$' + motor_idx, newvalue):
                        if self._moving_idx()!=motoridx:
                            # if no motor is moving or the moving motor is not
                            # this one, and the position of this motor has
                            # changed, save the motor positions
                            self._logger.debug(
                                'Position of motor %s on %s changed (to %f, raw %f), saving positions' % (
                                motor_idx, self._instancename, self._convert_pos_to_phys(value, motoridx), value))
                            self._save_positions()
                elif typenum == 2:  # targetspeed
                    self._update_variable(
                        'targetspeed$' + motor_idx, self._convert_speed_to_phys(value, motoridx))
                elif typenum == 3:  # actualspeed
                    self._update_variable(
                        'actualspeed$' + motor_idx, self._convert_speed_to_phys(value, motoridx))
                elif typenum == 4:
                    self._update_variable(
                        'maxspeed$' + motor_idx, self._convert_speed_to_phys(value, motoridx))
                elif typenum == 5:
                    self._update_variable(
                        'maxacceleration$' + motor_idx, self._convert_accel_to_phys(value, motoridx))
                elif typenum == 6:
                    self._update_variable(
                        'maxcurrent$' + motor_idx, self._convert_current_to_phys(value, motoridx))
                elif typenum == 7:
                    self._update_variable(
                        'standbycurrent$' + motor_idx, self._convert_current_to_phys(value, motoridx))
                elif typenum == 8:
                    self._update_variable(
                        'targetpositionreached$' + motor_idx, bool(value))
                elif typenum == 10:
                    self._update_variable(
                        'rightswitchstatus$' + motor_idx, bool(value))
                elif typenum == 11:
                    self._update_variable(
                        'leftswitchstatus$' + motor_idx, bool(value))
                elif typenum == 12:
                    self._update_variable(
                        'rightswitchenable$' + motor_idx, not bool(value))
                elif typenum == 13:
                    self._update_variable(
                        'leftswitchenable$' + motor_idx, not bool(value))
                elif typenum == 135:
                    self._update_variable(
                        'actualacceleration$' + motor_idx, self._convert_accel_to_phys(value, motoridx))
                elif typenum == 138:
                    self._update_variable('rampmode$' + motor_idx, value)
                elif typenum == 140:
                    self._update_variable(
                        'microstepresolution$' + motor_idx, value)
                elif typenum == 154:
                    self._update_variable(
                        'pulsedivisor$' + motor_idx, value)
                elif typenum == 153:
                    self._update_variable(
                        'rampdivisor$' + motor_idx, value)
                elif typenum == 204:
                    self._update_variable(
                        'freewheelingdelay$' + motor_idx, value / 1000)
                elif typenum == 206:
                    self._update_variable('load$' + motor_idx, value)
                elif typenum == 208:
                    self._update_variable(
                        'drivererror$' + motor_idx, value)
                else:
                    raise NotImplementedError(typenum)
            except TMCMConversionError:
                if self._has_all_variables():
                    self._logger.error('TMCM conversion error.')
            if ((self._moving_idx()== motoridx) and
                    (typenum in [0, 1, 3, 8, 10, 11])):
                # the current motor is moving and we just got updates to
                # one of the essential variables self._is_moving() is based
                # on. We must decide if the motor has stopped or not
                if not self._is_moving(motoridx):
                    # the motor has stopped
                    self._busyflag.release()
                    try:
                        del self._moving
                    except AttributeError:
                        # should not happen, but who knows.
                        pass
                    self._update_variable('_status', 'idle')
                    self._update_variable('_status$' + motor_idx, 'idle')
                    self._logger.debug('Saving positions for %s: moving just ended.' % self.name)
                    self._save_positions()
        elif cmdnum == 136:
            self._update_variable('firmwareversion', 'TMCM%d' % (
                value // 0x10000) + ', firmware v%d.%d' % ((value % 0x10000) / 0x100, value % 0x100))
        elif cmdnum == 4:
            # acknowledgement of start move
            self._moving['starttime'] = time.time()
        elif cmdnum == 3:
            # acknowledgement of stop
            pass
        elif cmdnum == 5:
            # acknowledgement of SAP
            pass
        elif cmdnum == 7:
            # acknowledgement of STAP
            pass
        else:
            raise NotImplementedError(cmdnum)
        if hasattr(self,'_moving'):
            # if we are moving, queue an immediate check for all variables.
            for vn in VOLATILE_VARIABLES:
                self.refresh_variable(vn + '$%d' % self._moving['index'], signal_needed=False)

    def _is_moving(self, motoridx):
        """Check if the motor is moving in the following way:

        1) check if a move has been initiated. If no => not moving
        2) if a move has been initiated but the confirmation for the initiating
            command has not yet arrived => moving
        3) if the current speed is nonzero => moving
        3) if the speed is zero, try to rule out movement by checking for
            common stop conditions:
            - limit switch hit => stop
            - targetpositionreached flag set => stop
        4) otherwise we assume that we are moving, even if the speed is zero.
            It can happen that the motor has not yet started.
        """

        try:
            if 'starttime' not in self._moving:
                # if we have not yet received the confirmation from the controller
                # to our MVP command, we are not stopped.
                return True
        except AttributeError:
            # `self` doesn't have a `_moving` attribute: no move has been
            # initiated: we assume that we are not moving.
            return False

        # In the following, check involving device variables are done. It is
        # important to use recent values, i.e. those received after the move
        # command has been confirmed, thus before using the values, their
        # timestamps will be checked.

        # check if the actual speed has been updated after the start of the
        # move, and if it has, see if it is zero. If not, we are moving.
        if self._timestamps['actualspeed$%d' % motoridx] > self._moving['starttime']:
            if self._properties['actualspeed$%d' % motoridx] != 0:
                return True


        # check the freshness of various parameters, i.e. if they have been
        # updated since we have received the ACK for the moving command.
        isfresh = [self._timestamps[prop + '$%d' % motoridx] > self._moving['starttime']
                   for prop in ['actualpositionraw', 'targetpositionraw',
                                'leftswitchstatus', 'rightswitchstatus']]
        if all(isfresh): # if all parameters have been refreshed
            # check if the corresponding limit switch is enabled and active
            actpos = self._properties['actualpositionraw$%d' % motoridx]
            targetpos = self._properties['targetpositionraw$%d' % motoridx]
            leftswitch = self._properties['leftswitchenable$%d' % motoridx] and self._properties[
                'leftswitchstatus$%d' % motoridx]
            rightswitch = self._properties['rightswitchenable$%d' % motoridx] and self._properties[
                'rightswitchstatus$%d' % motoridx]
            if ((targetpos - actpos) > 0 and rightswitch) or ((targetpos - actpos) < 0 and leftswitch):
                # moving to targetpos is inhibited by a limit switch
                self._logger.debug('Stopped by switch')
                return False

        # check if the target position is reached
        if self._timestamps['targetpositionreached$%d' % motoridx] > self._moving['starttime']:
            if self._properties['targetpositionreached$%d' % motoridx]:
                self._logger.debug('Target reached')
                return False

        # we could not rule out that we are moving
        return True

    def _convert_pos_to_phys(self, pos, motoridx):
        """Convert the raw value of position to physical dimensions.

        pos is in microsteps. The number of microsteps in a full step is 2**microstepresolution"""
        try:
            return pos / 2 ** self._properties['microstepresolution$%d' % motoridx] * self._full_step_size
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_pos_to_raw(self, pos, motoridx):
        """Convert the raw value of position to physical dimensions.

        pos is in microsteps. The number of microsteps in a full step is 2**microstepresolution"""
        try:
            return pos * 2 ** self._properties['microstepresolution$%d' % motoridx] / self._full_step_size
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_speed_to_phys(self, speed, motoridx):
        try:
            return speed / 2 ** (self._properties['pulsedivisor$%d' % motoridx] + self._properties[
                'microstepresolution$%d' % motoridx] + 16) * self._clock_frequency * self._full_step_size
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_speed_to_raw(self, speed, motoridx):
        try:
            return int(speed * 2 ** (self._properties['pulsedivisor$%d' % motoridx] + self._properties[
                'microstepresolution$%d' % motoridx] + 16) / self._clock_frequency / self._full_step_size)
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_accel_to_phys(self, accel, motoridx):
        try:
            return accel * self._full_step_size * self._clock_frequency ** 2 / 2 ** (
                self._properties['pulsedivisor$%d' % motoridx] + self._properties['rampdivisor$%d' % motoridx] +
                self._properties['microstepresolution$%d' % motoridx] + 29)
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_accel_to_raw(self, accel, motoridx):
        try:
            return int(accel / self._full_step_size / self._clock_frequency ** 2 * 2 ** (
                self._properties['pulsedivisor$%d' % motoridx] + self._properties['rampdivisor$%d' % motoridx] +
                self._properties['microstepresolution$%d' % motoridx] + 29))
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

    def moveto(self, motor:int, pos:float):
        """Move motor to the a given (physical) position.

        """
        if not self._positions_loaded.is_set():
            raise DeviceError('Cannot move motors until positions and soft limits have been loaded')
        if not self.get_variable('_status') == 'idle':
            raise DeviceError('Can only move if the controller is idle.')
        if not self._busyflag.acquire(False):
            raise DeviceError('Cannot start motor movement: one motor on the controller is moving')
        self.execute_command('moveto',motor, pos)

    def moverel(self, motor, pos):
        if not self._positions_loaded.is_set():
            raise DeviceError('Cannot move motors until positions and soft limits have been loaded')
        if not self.get_variable('_status') == 'idle':
            raise DeviceError('Can only move if the controller is idle.')
        if not self._busyflag.acquire(False):
            raise DeviceError('Cannot start motor movement: one motor on the controller is moving')
        self.execute_command('moverel',motor, pos)

    def stop(self, motor):
        self.execute_command('stop', motor)

    def calibrate(self, motor, pos):
        """Calibrate the position of the motor. To be called from the FRONTEND"""
        if not self._busyflag.acquire(False):
            raise DeviceError('Cannot calibrate: motor controller is busy')
        self.execute_command('calibrate', motor, pos)

    def _calibrate(self, motor, pos):
        """Calibrate the position of the motor. To be called from the BACKEND"""
        try:
            if not self.checklimits(motor, pos):
                raise DeviceError('Cannot calibrate outside soft limits')
            self.set_variable('rampmode$%d' % motor, 2)
            self.set_variable('actualposition$%d' % motor, pos)
            self.set_variable('targetposition$%d' % motor, pos)
        finally:
            self._busyflag.release()

    def where(self, motor):
        return self.get_variable('actualposition$%d' % motor)

    def _save_state(self):
        dic = Device_TCP._save_state(self)
        #        dic['softlimits'] = self._softlimits
        return dic

    def _on_startupdone(self):
        self._load_positions()
        self._update_variable('_status', 'idle')
        for i in range(self._motorcount):
            self._update_variable('_status$%d' % i, 'idle')
        #        for key in [k for k in self._properties if k.startswith('_status')]:
        #            self._update_variable(key, 'idle')
        return True

    def _execute_command(self, commandname, arguments):
        if commandname in ['moveto', 'moverel']:
            # handle moving commands
            motor, pos = arguments
            try:
                # Check the validity of the motor index
                assert((motor >= 0) and (motor < self._N_axes))
                # if another motor is moving (not expected to happen,
                # since self._busyflag should ensure this, but
                # anyway...
                assert(not hasattr(self,'_moving'))
                # get actual position
                where = self._properties['actualposition$%d' % motor]
                if commandname == 'moveto':
                    relpos = pos - where
                    abspos = pos
                else:
                    relpos = pos
                    abspos = pos + where
                if relpos == 0:
                    # do not execute null-moves.
                    self._busyflag.release()
                    self._update_variable('_status', 'idle', force=True)
                    self._update_variable(
                        '_status$%d' % motor, 'idle', force=True)
                    return

                # check soft limits: do not allow movement to go outside them.
                if not self.checklimits(motor, abspos):
                    raise DeviceError(
                        'Cannot move motor %d, requested position outside soft limits' % motor, '_status$%d' % motor)
                # check status of right and left limit switches: if they are
                # active, do not start motors.
                if ((relpos > 0) and
                        (self._properties['rightswitchstatus$%d' % motor] and
                             self._properties['rightswitchenable$%d' % motor])):
                    self._logger.error('Right limit switch active before move')
                    raise DeviceError('Cannot move motor %d to the right: limit switch active' % motor,
                                      '_status$%d' % motor)
                if ((relpos < 0) and
                        (self._properties['leftswitchstatus$%d' % motor] and
                             self._properties['leftswitchenable$%d' % motor])):
                    self._logger.error('Left limit switch active before move')
                    raise DeviceError('Cannot move motor %d to the left: limit switch active' % motor,
                                      '_status$%d' % motor)
                # we need and can move. Issue the command.
                posraw = self._convert_pos_to_raw(pos, motor)
                self._moving = {'index': motor, 'startposition': self._properties['actualpositionraw$%d' % motor]}
                self._update_variable('_status', 'Moving #%d' % motor)
                self._update_variable('_status$%d' % motor, 'Moving')
                self._send(self._construct_tmcl_command(4, int(commandname == 'moverel'), motor, posraw))
            except Exception as exc:
                # if an error happened above, we are not moving.
                self._busyflag.release()
                self._logger.warning('Exception while starting move: ' + str(exc))
                try:
                    del self._moving
                except AttributeError:
                    pass
                # force updates on _status: this will ensure that higher-level
                # motor interfaces will issue stop signals
                self._update_variable('_status', 'idle', force=True)
                self._update_variable('_status$%d' % motor, 'idle', force=True)
                raise
        elif commandname == 'stop':
            motor = arguments
            self._send(self._construct_tmcl_command(3, 0, motor, 0))
        elif commandname == 'load_positions':
            self._load_positions()
        elif commandname == 'save_positions':
            self._save_positions()
        elif commandname == 'calibrate':
            self._calibrate(*arguments)
        else:
            raise UnknownCommand(commandname)

    def _set_variable(self, variable, value):
        self._logger.debug('Set_variable in %s: %s <- %s' % (self._instancename, variable, str(value)))

        try:
            motor_idx = int(variable.split('$')[1])
            assert((motor_idx>=0) and (motor_idx<self._N_axes))
        except (IndexError, ValueError):
            motor_idx = None
        try:
            if variable.startswith('targetposition$'):
                self._send(self._construct_tmcl_command(
                    5, 0, motor_idx, self._convert_pos_to_raw(
                        value, motor_idx)))
            elif variable.startswith('actualposition$'):
                self._send(self._construct_tmcl_command(
                    5, 1, motor_idx, self._convert_pos_to_raw(
                        value, motor_idx)))
            elif variable.startswith('targetspeed$'):
                self._send(self._construct_tmcl_command(
                    5, 2, motor_idx, self._convert_speed_to_raw(
                        value, motor_idx)))
            elif variable.startswith('actualspeed$'):
                self._send(self._construct_tmcl_command(
                    5, 3, motor_idx, self._convert_speed_to_raw(
                        value, motor_idx)))
            elif variable.startswith('maxspeed$'):
                self._send(self._construct_tmcl_command(
                    5, 4, motor_idx, self._convert_speed_to_raw(
                        value, motor_idx)))
                self._send(self._construct_tmcl_command(
                    7, 4, motor_idx, 0)) # issue a STAP command as well
            elif variable.startswith('maxacceleration$'):
                self._send(self._construct_tmcl_command(
                    5, 5, motor_idx, self._convert_accel_to_raw(
                        value, motor_idx)))
                self._send(self._construct_tmcl_command(
                    7, 5, motor_idx, 0))
            elif variable.startswith('maxcurrent$'):
                self._send(
                    self._construct_tmcl_command(5, 6, motor_idx,
                                                 self._convert_current_to_raw(value, motor_idx)))
            elif variable.startswith('standbycurrent$'):
                self._send(
                    self._construct_tmcl_command(5, 7, motor_idx,
                                                 self._convert_current_to_raw(value, motor_idx)))
            elif variable.startswith('rightswitchenable$'):
                self._send(
                    self._construct_tmcl_command(5, 12, motor_idx, not bool(value)))
                self._send(
                    self._construct_tmcl_command(7, 12, motor_idx, 0))
            elif variable.startswith('leftswitchenable$'):
                self._send(
                    self._construct_tmcl_command(5, 13, motor_idx, not bool(value)))
                self._send(
                    self._construct_tmcl_command(7, 13, motor_idx, 0))
            elif variable.startswith('rampmode$'):
                if value not in [0, 1, 2]:
                    raise ValueError('Invalid ramp mode: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 138, motor_idx, value))
            elif variable.startswith('microstepresolution$'):
                if value < 0 or value > self._max_microsteps:
                    raise ValueError(
                        'Invalid microstep resolution: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 140, motor_idx, value))
                self._send(
                    self._construct_tmcl_command(7, 140, motor_idx, 0))
            elif variable.startswith('rampdivisor$'):
                if value < 0 or value > 13:
                    raise ValueError('Invalid ramp divisor: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 153, motor_idx, value))
                self._send(
                    self._construct_tmcl_command(7, 153, motor_idx, 0))
            elif variable.startswith('pulsedivisor$'):
                if value < 0 or value > 13:
                    raise ValueError('Invalid pulse divisor: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 154, motor_idx, value))
                self._send(
                    self._construct_tmcl_command(7, 154, motor_idx, 0))
            elif variable.startswith('freewheelingdelay$'):
                if value < 0 or value > 65.535:
                    raise ValueError('Invalid freewheeling delay: %d' % value)
                self._send(
                    self._construct_tmcl_command(5, 204, motor_idx, value * 1000))
                self._send(
                    self._construct_tmcl_command(7, 204, motor_idx, 0))
            elif variable.startswith('softleft$'):
                if self._update_variable(variable, value):
                    self._save_positions()
            elif variable.startswith('softright$'):
                if self._update_variable(variable, value):
                    self._save_positions()
            elif variable in self._all_variables:
                raise ReadOnlyVariable(variable)
            else:
                raise UnknownVariable(variable)
        except TMCMConversionError:
            self._queue_to_backend.put_nowait(('set', variable, value))

    def _save_positions(self):
        if not self._positions_loaded.is_set():
            # avoid overwriting the position file before it can be loaded.
            self._logger.debug(
                'Not saving positions yet (process %s): file exists and up to now no complete loading happened.' % multiprocessing.current_process().name)
            return
        posfile = ''
        try:
            for mot in range(self._motorcount):
                posfile+= '%d: %g (%g, %g)\n' % (
                    mot, self.where(mot), self._properties['softleft$%d' % mot],
                    self._properties['softright$%d' % mot])
        except KeyError as ke:
            self._logger.error('Error saving motor position file for controller %s, because of missing key: %s' % (
            self._instancename, ke.args[0]))
            return
        with open(os.path.join(self.configdir, self._instancename + '.motorpos'), 'wt', encoding='utf-8') as f:
            f.write(posfile)
        self._logger.debug('Positions saved for controller %s' % self._instancename)

    def _load_positions(self):
        self._logger.debug('Loading positions for controller %s' % self._instancename)
        if not self._busyflag.acquire(False):
            raise DeviceError(
                'Cannot load positions from file if motor is moving!')
        try:
            with open(os.path.join(self.configdir, self._instancename + '.motorpos'), 'rt', encoding='utf-8') as f:
                loaded = []
                lines = 0
                for l in f:
                    lines += 1
                    m = re.match('(?P<motoridx>\d+): (?P<position>' + RE_FLOAT +
                                 ') \((?P<leftlim>' + RE_FLOAT + '), (?P<rightlim>' + RE_FLOAT + ')\)', l)
                    if not m:
                        raise DeviceError(
                            'Invalid line in motor position file: ' + l)
                    gd = m.groupdict()
                    idx = int(gd['motoridx'])
                    self._update_variable('softleft$%d' % idx, float(gd['leftlim']))
                    self._update_variable('softright$%d' % idx, float(gd['rightlim']))
                    if 'actualposition$%d' % idx not in self._properties:
                        self._logger.warning(
                            'Actualposition for motor %d on controller %s not yet received. Not calibrating.' % (
                                idx, self._instancename))
                        continue
                    else:
                        if abs(self._properties['actualposition$%d' % idx] - float(gd['position'])) > 0.001:
                            self._logger.warning(
                                'Current position (%.3f) of motor %d on controller %s differs from the stored one (%.3f): calibrating to the stored value.' % (
                                    self._properties['actualposition$%d' % idx], idx, self._instancename,
                                    float(gd['position'])))
                            self._calibrate(idx, float(gd['position']))
                        loaded.append(idx)
                if lines != self._motorcount:
                    self._logger.error('Invalid motor position file: ' + os.path.join(self.configdir,
                                                                                      self._instancename + '.motorpos'))
                    for i in range(self._motorcount):
                        self._update_variable('softleft$%d' % i, -100)
                        self._update_variable('softright$%d' % i, 100)
                    self._positions_loaded.set()
            if len(loaded) == self._motorcount:
                self._logger.info('Positions loaded for controller %s in process %s' % (
                    self._instancename, multiprocessing.current_process().name))
                self._positions_loaded.set()
        except FileNotFoundError:
            self._logger.info('Positions loaded (no file) for controller %s in process %s' % (
                self._instancename, multiprocessing.current_process().name))
            for i in range(self._motorcount):
                self._update_variable('softleft$%d' % i, -100)
                self._update_variable('softright$%d' % i, 100)
            self._positions_loaded.set()
        finally:
            self._busyflag.release()

    def _initialize_after_connect(self):
        Device_TCP._initialize_after_connect(self)
        self.refresh_variable('firmwareversion', check_backend_alive=False)

    def moving(self):
        return self._moving is not None

    def checklimits(self, motor, position):
        return (position >= self._properties['softleft$%d' % motor]) and \
               (position <= self._properties['softright$%d' % motor])

    def set_limits(self, index, left=None, right=None):
        if left is not None:
            self.set_variable('softleft$%d' % index, left)
        if right is not None:
            self.set_variable('softright$%d' % index, right)

    def get_limits(self, index):
        return self._properties['softleft$%d' % index], self._properties['softright$%d' % index]

    def save_positions(self):
        self.execute_command('save_positions')


class TMCM351(TMCMcard):
    def __init__(self, *args, **kwargs):
        TMCMcard.__init__(self, *args, **kwargs)
        self._motorcount = 3
        self._top_rms_current = 2.8
        self._motor_indices = [0, 1, 2]
        self._max_microsteps = 6
        for i in range(self._motorcount):
            self._properties['softleft$%d' % i] = -100
            self._properties['softright$%d' % i] = 100

    def decode_error_flags(self, flags):
        lis = []
        if flags & 0b1:
            lis.append('Overcurrent bridge A low side')
        if flags & 0b10:
            lis.append('Overcurrent bridge B low side')
        if flags & 0b100:
            lis.append('Open load bridge A')
        if flags & 0b1000:
            lis.append('Open load bridge B')
        if flags & 0b10000:
            lis.append('Overcurrent high side')
        if flags & 0b100000:
            lis.append('Driver undervoltage')
        if flags & 0b1000000:
            lis.append('Temperature warning')
        if flags & 0b10000000:
            lis.append('Overtemperature')
        return lis


class TMCM6110(TMCMcard):
    def __init__(self, *args, **kwargs):
        TMCMcard.__init__(self, *args, **kwargs)
        self._motorcount = 6
        self._top_rms_current = 1.1
        self._motor_indices = [0, 1, 2, 3, 4, 5]
        self._max_microsteps = 8
        for i in range(self._motorcount):
            self._properties['softleft$%d' % i] = -100
            self._properties['softright$%d' % i] = 100

    def decode_error_flags(self, flags):
        lis = []
        if flags & 0b1:
            lis.append('stallGuard2 threshold reached')
        if flags & 0b10:
            lis.append('Overtemperature')
        if flags & 0b100:
            lis.append('Pre-warning overtemperature')
        if flags & 0b1000:
            lis.append('Short to ground A')
        if flags & 0b10000:
            lis.append('Short to ground B')
        if flags & 0b100000:
            lis.append('Open load A')
        if flags & 0b1000000:
            lis.append('Open load B')
        if flags & 0b10000000:
            lis.append('Stand still')
        return lis
