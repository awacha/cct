import itertools
import logging
import multiprocessing
import operator
import os
import re
import struct
import time
from typing import List

from ..device import DeviceBackend_TCP, DeviceError, UnknownCommand, UnknownVariable, ReadOnlyVariable, InvalidValue, \
    Device
from ..device.message import Message

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
                       'actualacceleration', 'softleft', 'softright']

DEVICE_VARIABLES = ['firmwareversion']

TMCL_ERROR_MESSAGES = {1: 'wrong checksum',
                       2: 'invalid command',
                       3: 'wrong type',
                       4: 'invalid value',
                       5: 'configuration EEPROM locked',
                       6: 'command not available',
                       100: 'unspecified error',
                       }


class TMCMConversionError(DeviceError):
    pass


# noinspection PyPep8Naming
class TMCMCard_Backend(DeviceBackend_TCP):
    """Motor controller card from Trinamic GmbH, Hamburg, Germany. Developed for TMCM351 and TMCM6110, may or may not
    work for other models."""

    def __init__(self, *args, **kwargs):
        self.N_axes = kwargs['N_axes']
        del kwargs['N_axes']
        self.top_RMS_current = kwargs['top_RMS_current']
        del kwargs['top_RMS_current']
        self.max_microsteps = kwargs['max_microsteps']
        del kwargs['max_microsteps']
        self.clock_frequency = kwargs['clock_frequency']
        del kwargs['clock_frequency']
        self.full_step_size = kwargs['full_step_size']
        del kwargs['full_step_size']
        self.positions_loaded = kwargs['positions_loaded']
        del kwargs['positions_loaded']
        for arg in ['N_axes', 'top_RMS_current', 'max_microsteps', 'clock_frequency', 'full_step_size',
                    'positions_loaded']:
            setattr(self, arg, kwargs[arg])
            del kwargs[arg]
        super().__init__(*args, **kwargs)
        # status information dictionary when a motor is moving, None otherwise.
        # dictionary keys:
        #    index: the axis index of the currently moving motor
        self._moving = None
        self.original_urgency_modulo = self.urgency_modulo

    def query_variable(self, variablename: str):
        try:
            motor_idx = int(variablename.split('$')[1])
            if (motor_idx < 0) or (motor_idx >= self.N_axes):
                raise UnknownVariable(variablename)
        except (IndexError, ValueError):
            motor_idx = None
        if variablename == 'firmwareversion':
            self.send_tmcl_command(136, 1, 0, 0)
        elif variablename.startswith('targetposition$') or variablename.startswith('targetpositionraw$'):
            self.send_tmcl_command(6, 0, motor_idx, 0)
        elif variablename.startswith('actualposition$') or variablename.startswith('actualpositionraw$'):
            self.send_tmcl_command(6, 1, motor_idx, 0)
        elif variablename.startswith('targetspeed$'):
            self.send_tmcl_command(6, 2, motor_idx, 0)
        elif variablename.startswith('actualspeed$'):
            self.send_tmcl_command(6, 3, motor_idx, 0)
        elif variablename.startswith('maxspeed$'):
            self.send_tmcl_command(6, 4, motor_idx, 0)
        elif variablename.startswith('maxacceleration$'):
            self.send_tmcl_command(6, 5, motor_idx, 0)
        elif variablename.startswith('maxcurrent$'):
            self.send_tmcl_command(6, 6, motor_idx, 0)
        elif variablename.startswith('standbycurrent$'):
            self.send_tmcl_command(6, 7, motor_idx, 0)
        elif variablename.startswith('targetpositionreached$'):
            self.send_tmcl_command(6, 8, motor_idx, 0)
        elif variablename.startswith('rightswitchstatus$'):
            self.send_tmcl_command(6, 10, motor_idx, 0)
        elif variablename.startswith('leftswitchstatus$'):
            self.send_tmcl_command(6, 11, motor_idx, 0)
        elif variablename.startswith('rightswitchenable$'):
            self.send_tmcl_command(6, 12, motor_idx, 0)
        elif variablename.startswith('leftswitchenable$'):
            self.send_tmcl_command(6, 13, motor_idx, 0)
        elif variablename.startswith('actualacceleration$'):
            self.send_tmcl_command(6, 135, motor_idx, 0)
        elif variablename.startswith('rampmode$'):
            self.send_tmcl_command(6, 138, motor_idx, 0)
        elif variablename.startswith('microstepresolution$'):
            self.send_tmcl_command(6, 140, motor_idx, 0)
        elif variablename.startswith('rampdivisor$'):
            self.send_tmcl_command(6, 153, motor_idx, 0)
        elif variablename.startswith('pulsedivisor$'):
            self.send_tmcl_command(6, 154, motor_idx, 0)
        elif variablename.startswith('freewheelingdelay$'):
            self.send_tmcl_command(6, 204, motor_idx, 0)
        elif variablename.startswith('load$'):
            self.send_tmcl_command(6, 206, motor_idx, 0)
        elif variablename.startswith('drivererror$'):
            self.send_tmcl_command(6, 208, motor_idx, 0)
        elif variablename.startswith('softleft$') or variablename.startswith('softright$'):
            # these variables are not known to the hardware, the values are
            # stored here in this class.
            if variablename not in self.properties:
                if variablename.startswith('softleft$'):
                    self.update_variable(variablename, 0)
                elif variablename.startswith('softright$'):
                    self.update_variable(variablename, 0)
                else:
                    assert False
            self.update_variable(variablename, self.properties[variablename])
        else:
            raise UnknownVariable(variablename)

    @staticmethod
    def get_complete_messages(message):
        messages = []
        # messages from the TMCM cards always consist of 9 bytes.
        while len(message) >= 9:
            messages.append(message[:9])
            message = message[9:]
        # now add the remainder as the last item of the list
        messages.append(message)
        return messages

    def moving_idx(self):
        """Get the index of the currently moving motor. If no motor is moving,
        return None."""
        try:
            return self._moving['index']
        except (AttributeError, TypeError):
            return None

    def process_incoming_message(self, message, original_sent=None):
        # check the checksum on the message
        if (sum(message[:-1]) % 256) != message[-1]:
            raise DeviceError(
                'Invalid message (checksum error): ' + str(message))
        # check the status code of the message:
        status = message[2]
        if status != 100:
            raise DeviceError('TMCL error: {} in message: {}'.format(
                TMCL_ERROR_MESSAGES[status], str(message)))
        cmdnum = message[3]
        if cmdnum != original_sent[1]:
            raise DeviceError('Invalid reply: command number not the same.')
        value = struct.unpack('>i', message[4:8])[0]
        if cmdnum == 6:  # get axis parameter
            typenum = original_sent[2]
            motor_idx = str(original_sent[3])
            motoridx = original_sent[3]
            try:
                if typenum == 0:  # targetposition
                    self.update_variable('targetposition$' + motor_idx,
                                         self._convert_pos_to_phys(value,
                                                                   motoridx))
                    self.update_variable('targetpositionraw$' + motor_idx,
                                         value)
                elif typenum == 1:  # actualposition
                    newvalue = self._convert_pos_to_phys(value, motoridx)
                    self.update_variable('actualpositionraw$' + motor_idx,
                                         value)
                    if self.update_variable('actualposition$' + motor_idx,
                                            newvalue):
                        if self.moving_idx() != motoridx:
                            # if no motor is moving or the moving motor is not
                            # this one, and the position of this motor has
                            # changed, save the motor positions
                            self.logger.debug(
                                'Position of motor {} on {} changed (to {:f}, raw {:f}), saving positions.'.format(
                                    motor_idx, self.name, self._convert_pos_to_phys(value, motoridx), value))
                            self.save_positions()
                elif typenum == 2:  # targetspeed
                    self.update_variable('targetspeed$' + motor_idx,
                                         self._convert_speed_to_phys(
                                             value, motoridx))
                elif typenum == 3:  # actualspeed
                    self.update_variable('actualspeed$' + motor_idx,
                                         self._convert_speed_to_phys(value, motoridx))
                elif typenum == 4:
                    self.update_variable(
                        'maxspeed$' + motor_idx,
                        self._convert_speed_to_phys(value, motoridx))
                elif typenum == 5:
                    self.update_variable(
                        'maxacceleration$' + motor_idx,
                        self._convert_accel_to_phys(value, motoridx))
                elif typenum == 6:
                    self.update_variable(
                        'maxcurrent$' + motor_idx,
                        self._convert_current_to_phys(value))
                elif typenum == 7:
                    self.update_variable(
                        'standbycurrent$' + motor_idx,
                        self._convert_current_to_phys(value))
                elif typenum == 8:
                    self.update_variable('targetpositionreached$' + motor_idx,
                                         bool(value))
                elif typenum == 10:
                    self.update_variable('rightswitchstatus$' + motor_idx,
                                         bool(value))
                elif typenum == 11:
                    self.update_variable('leftswitchstatus$' + motor_idx,
                                         bool(value))
                elif typenum == 12:
                    # the corresponding register in the TMCM card is "Right
                    # limit switch DISABLE".
                    self.update_variable('rightswitchenable$' + motor_idx,
                                         not bool(value))
                elif typenum == 13:
                    # the corresponding register in the TMCM card is "Left
                    # limit switch DISABLE".
                    self.update_variable('leftswitchenable$' + motor_idx,
                                         not bool(value))
                elif typenum == 135:
                    self.update_variable(
                        'actualacceleration$' + motor_idx,
                        self._convert_accel_to_phys(value, motoridx))
                elif typenum == 138:
                    self.update_variable('rampmode$' + motor_idx, value)
                elif typenum == 140:
                    self.update_variable('microstepresolution$' + motor_idx,
                                         value)
                elif typenum == 154:
                    self.update_variable('pulsedivisor$' + motor_idx, value)
                elif typenum == 153:
                    self.update_variable('rampdivisor$' + motor_idx, value)
                elif typenum == 204:
                    self.update_variable('freewheelingdelay$' + motor_idx,
                                         value / 1000)
                elif typenum == 206:
                    self.update_variable('load$' + motor_idx, value)
                elif typenum == 208:
                    self.update_variable('drivererror$' + motor_idx, value)
                else:
                    raise ValueError(typenum)
            except TMCMConversionError:
                # if we reach this, _update_variable() has not been called with
                # the new value. We must manually remove the variable name from
                # self._query_requested, in order to allow re-querying it.
                if self.has_all_variables():
                    # Some TMCMConversionErrors are expected until all the
                    # variables have been obtained.
                    self.logger.error('TMCM conversion error.')
                return False
            if ((self.moving_idx() == motoridx) and
                    (typenum in [0, 1, 3, 8, 10, 11])):
                # the current motor is moving and we just got updates to
                # one of the essential variables self._is_moving() is based
                # on. We must decide if the motor has stopped or not
                if not self.is_moving(motoridx):
                    self.on_motor_stopped(motoridx)
        elif cmdnum == 136:
            self.update_variable('firmwareversion', 'TMCM{:d}, firmware v{:d}.{:d}'.format(
                value // 0x10000, (value % 0x10000) // 0x100, value % 0x100))
        elif cmdnum == 4:
            # acknowledgement of start move
            self._moving['acktime'] = time.time()
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
            raise ValueError(cmdnum)

    def on_motor_start(self, motoridx: int, startposition: float):
        """Executed when a motor starts moving."""
        self.update_variable('_status', 'Moving #' + str(motoridx))
        self.update_variable('_status$' + str(motoridx), 'Moving')
        self._moving = {'index': motoridx,
                        'starttime': time.monotonic(),
                        'acktime': None,
                        'startposition': startposition,
                        }
        # From now on, until the motor stops, only urgent variables will be
        # queried. The urgent variables are the volatile variables of this
        # motor.
        self.urgent_variables = [vn + '$' + str(motoridx) for vn in VOLATILE_VARIABLES]
        self.urgency_modulo = 0

    def on_motor_stopped(self, motoridx):
        """This method performs the housekeeping tasks when a motor is stopped."""
        try:
            self.busysemaphore.release()
        except ValueError:
            pass
        self._moving = None
        self.urgent_variables = []
        self.urgency_modulo = self.original_urgency_modulo
        self.update_variable('_status', 'idle', force=True)
        self.update_variable('_status$' + str(motoridx), 'idle', force=True)
        # self._logger.debug('Saving positions for '+self.name+': moving just ended.')
        self.save_positions()

    def is_moving(self, motoridx: int):
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
        motoridx = str(motoridx)
        if self._moving is None:
            # no move has been initiated: we assume that we are not moving
            return False
        if 'acktime' not in self._moving:
            # if we have not yet received the confirmation from the controller
            # to our MVP command, we are not stopped.
            return True

        # In the following, check involving device variables are done. It is
        # important to use recent values, i.e. those received after the move
        # command has been confirmed, thus before using the values, their
        # timestamps will be checked.

        # check if the target position is reached
        if self.timestamps['targetpositionreached$' + motoridx] > self._moving['starttime']:
            if self.properties['targetpositionreached$' + motoridx]:
                self.logger.debug('Target reached')
                return False

        # check if the actual speed has been updated after the start of the
        # move, and if it has, see if it is zero. If not, we are moving.
        if self.timestamps['actualspeed$' + motoridx] > self._moving['starttime']:
            if self.properties['actualspeed$' + motoridx] != 0:
                return True

        # check the freshness of various parameters, i.e. if they have been
        # updated since we have received the ACK for the moving command.
        isfresh = [self.timestamps[prop + '$' + motoridx] > self._moving['starttime']
                   for prop in ['actualpositionraw', 'targetpositionraw',
                                'leftswitchstatus', 'rightswitchstatus']]
        if all(isfresh):  # if all parameters have been refreshed
            # check if the corresponding limit switch is enabled and active
            actpos = self.properties['actualpositionraw$' + motoridx]
            targetpos = self.properties['targetpositionraw$' + motoridx]
            leftswitch = self.properties['leftswitchenable$' + motoridx] and self.properties[
                'leftswitchstatus$' + motoridx]
            rightswitch = self.properties['rightswitchenable$' + motoridx] and self.properties[
                'rightswitchstatus$' + motoridx]
            if ((targetpos - actpos) > 0 and rightswitch) or ((targetpos - actpos) < 0 and leftswitch):
                # moving to targetpos is inhibited by a limit switch
                self.logger.debug('Stopped by switch')
                return False

        # we could not rule out that we are moving
        return True

    def _convert_pos_to_phys(self, pos: int, motoridx: int) -> float:
        """Convert the raw value of position to physical dimensions.

        pos is in microsteps. The number of microsteps in a full step is 2**microstepresolution"""
        try:
            return pos / 2 ** self.properties['microstepresolution$' + str(motoridx)] * self.full_step_size
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_pos_to_raw(self, pos: float, motoridx: int) -> int:
        """Convert the raw value of position to physical dimensions.

        pos is in microsteps. The number of microsteps in a full step is 2**microstepresolution"""
        try:
            return int(pos * 2 ** self.properties['microstepresolution$' + str(motoridx)] / self.full_step_size)
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_speed_to_phys(self, speed: int, motoridx: int) -> float:
        try:
            return speed / 2 ** (self.properties['pulsedivisor$' + str(motoridx)] + self.properties[
                'microstepresolution$' + str(motoridx)] + 16) * self.clock_frequency * self.full_step_size
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_speed_to_raw(self, speed: float, motoridx: int) -> int:
        try:
            return int(speed * 2 ** (self.properties['pulsedivisor$' + str(motoridx)] + self.properties[
                'microstepresolution$' + str(motoridx)] + 16) / self.clock_frequency / self.full_step_size)
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_accel_to_phys(self, accel: int, motoridx: int) -> float:
        try:
            return accel * self.full_step_size * self.clock_frequency ** 2 / 2 ** (
                self.properties['pulsedivisor$' + str(motoridx)] + self.properties['rampdivisor$' + str(motoridx)] +
                self.properties['microstepresolution$' + str(motoridx)] + 29)
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_accel_to_raw(self, accel: float, motoridx: int) -> int:
        try:
            return int(accel / self.full_step_size / self.clock_frequency ** 2 * 2 ** (
                self.properties['pulsedivisor$' + str(motoridx)] + self.properties['rampdivisor$' + str(motoridx)] +
                self.properties['microstepresolution$' + str(motoridx)] + 29))
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_current_to_phys(self, current: int) -> float:
        try:
            return current * self.top_RMS_current / 255
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def _convert_current_to_raw(self, current: float) -> int:
        try:
            return int(current * 255 / self.top_RMS_current)
        except KeyError as ke:
            raise TMCMConversionError(ke)

    def send_tmcl_command(self, cmdnum: int, typenum: int, motor_or_bank: int, value: int) -> bytes:
        """Construct the bytes representation of the command and send it to the
        TMCM card. The bytes are:
        - Module address (always 1)
        - Command number
        - Type number
        - Motor or Bank number
        - Value (MSB)
        - Value
        - Value
        - Value (LSB)
        - Checksum: the sum of all the previous bytes, module 256.

        In total, 9 bytes compose the sent message.
        """
        cmd = bytes([1, cmdnum, typenum, motor_or_bank]) + struct.pack('>i', int(value))
        cmd = cmd + bytes([sum(cmd) % 256])
        self.send_message(cmd, expected_replies=1, asynchronous=False)
        return cmd

    def calibrate(self, motor, pos, release_busysemaphore=True):
        """Calibrate the position of the motor. To be called from the BACKEND"""
        try:
            if not self.checklimits(motor, pos):
                raise DeviceError('Cannot calibrate outside soft limits')
            self.set_variable('rampmode$' + str(motor), 2)
            self.set_variable('actualposition$' + str(motor), pos)
            self.set_variable('targetposition$' + str(motor), pos)
            self.save_positions()
        finally:
            if release_busysemaphore:
                self.busysemaphore.release()

    def on_startupdone(self):
        # initialization after all variables have been obtained
        self.load_positions()  # load the positions from the state file.
        self.update_variable('_status', 'idle')  # set our status to idle.
        for i in range(self.N_axes):
            self.update_variable('_status$' + str(i), 'idle')
        super().on_startupdone()
        return True

    def execute_command(self, commandname, arguments):
        if commandname in ['moveto', 'moverel']:
            # handle moving commands
            motor, pos = arguments
            self.logger.debug('Starting {} of motor {:d} to {:f}'.format(commandname, motor, pos))
            try:
                # before issuing the moveto/moverel command, check if we are
                # safe to do so.

                # Check the validity of the motor index
                if motor < 0 or motor >= self.N_axes:
                    raise InvalidValue(motor)
                # if another motor is moving (not expected to happen,
                # since the busysemaphore should ensure this, but anyway...
                assert self._moving is None
                # get the actual position
                where = self.properties['actualposition$' + str(motor)]
                if commandname == 'moveto':
                    relpos = pos - where
                    abspos = pos
                else:
                    relpos = pos
                    abspos = pos + where
                # relpos: relative movement from the current position.
                # abspos: absolute target position
                if relpos == 0:
                    # do not execute null-moves. Act as if the movement
                    # has already finished.
                    self.on_motor_stopped(motor)
                    return
                # check soft limits: do not allow movement to go outside them.
                if not self.checklimits(motor, abspos):
                    raise DeviceError(
                        'Cannot move motor {:d}, requested position outside soft limits'.format(motor),
                        '_status$' + str(motor))
                # check status of right and left limit switches: if they are
                # active, do not start motors.
                for side, cmp in [('right', operator.gt), ('left', operator.lt)]:
                    if (cmp(relpos, 0) and
                            self.properties[side + 'switchstatus$' + str(motor)] and
                            self.properties[side + 'switchenable$' + str(motor)]):
                        self.logger.error('Cannot start motor {:d}: {} limit switch active'.format(motor, side))
                        raise DeviceError('Cannot move motor {:d} to the right: limit switch active'.format(motor),
                                          '_status$' + str(motor))
                # If we survived, then we need and can move. Issue the command.
                posraw = self._convert_pos_to_raw(pos, motor)
                self.on_motor_start(motor, self.properties['actualpositionraw$' + str(motor)])
                self.send_tmcl_command(4, int(commandname == 'moverel'), motor, posraw)
                self.logger.debug('Issued move command.')
            except Exception as exc:
                # if an error happened above, we are not moving. Act if we have stopped.
                self.on_motor_stopped(motor)
                self.logger.warning('Exception while starting move: ' + str(exc))
                raise
        elif commandname == 'stop':
            motor = arguments[0]
            self.send_tmcl_command(3, 0, motor, 0)
        elif commandname == 'load_positions':
            self.load_positions()
        elif commandname == 'save_positions':
            self.save_positions()
        elif commandname == 'calibrate':
            self.calibrate(*arguments)
        else:
            raise UnknownCommand(commandname)

    def set_variable(self, variable: str, value: object):
        self.logger.debug('Set_variable in {}: {} <- {}'.format(self.name, variable, str(value)))
        try:
            motor_idx = int(variable.split('$')[1])
            if motor_idx < 0 or motor_idx >= self.N_axes:
                raise InvalidValue(motor_idx)
        except (IndexError, ValueError):
            motor_idx = None
        try:
            if variable.startswith('targetposition$'):
                assert isinstance(value, float)
                self.send_tmcl_command(
                    5, 0, motor_idx, self._convert_pos_to_raw(
                        value, motor_idx))
            elif variable.startswith('actualposition$'):
                assert isinstance(value, float)
                self.send_tmcl_command(
                    5, 1, motor_idx, self._convert_pos_to_raw(
                        value, motor_idx))
            elif variable.startswith('targetspeed$'):
                assert isinstance(value, float)
                self.send_tmcl_command(
                    5, 2, motor_idx, self._convert_speed_to_raw(
                        value, motor_idx))
            elif variable.startswith('actualspeed$'):
                assert isinstance(value, float)
                self.send_tmcl_command(
                    5, 3, motor_idx, self._convert_speed_to_raw(
                        value, motor_idx))
            elif variable.startswith('maxspeed$'):
                assert isinstance(value, float)
                self.send_tmcl_command(
                    5, 4, motor_idx, self._convert_speed_to_raw(
                        value, motor_idx))
                self.send_tmcl_command(
                    7, 4, motor_idx, 0)  # issue a STAP command as well
            elif variable.startswith('maxacceleration$'):
                assert isinstance(value, float)
                self.send_tmcl_command(
                    5, 5, motor_idx, self._convert_accel_to_raw(
                        value, motor_idx))
                self.send_tmcl_command(
                    7, 5, motor_idx, 0)  # issue a STAP command as well
            elif variable.startswith('maxcurrent$'):
                assert isinstance(value, float)
                self.send_tmcl_command(
                    5, 6, motor_idx, self._convert_current_to_raw(
                        value))
            elif variable.startswith('standbycurrent$'):
                assert isinstance(value, float)
                self.send_tmcl_command(
                    5, 7, motor_idx, self._convert_current_to_raw(
                        value))
            elif variable.startswith('rightswitchenable$'):
                self.send_tmcl_command(
                    5, 12, motor_idx, not bool(value))
                self.send_tmcl_command(
                    7, 12, motor_idx, 0)  # issue a STAP command as well
            elif variable.startswith('leftswitchenable$'):
                self.send_tmcl_command(
                    5, 13, motor_idx, not bool(value))
                self.send_tmcl_command(
                    7, 13, motor_idx, 0)  # issue a STAP command as well
            elif variable.startswith('rampmode$'):
                assert isinstance(value, int)
                if value not in [0, 1, 2]:
                    raise InvalidValue('Invalid ramp mode: ' + str(value))
                self.send_tmcl_command(
                    5, 138, motor_idx, value)
            elif variable.startswith('microstepresolution$'):
                assert isinstance(value, int)
                if value < 0 or value > self.max_microsteps:
                    raise InvalidValue(
                        'Invalid microstep resolution: ' + str(value))
                self.send_tmcl_command(
                    5, 140, motor_idx, value)
                self.send_tmcl_command(
                    7, 140, motor_idx, 0)  # issue a STAP command as well
            elif variable.startswith('rampdivisor$'):
                assert isinstance(value, int)
                if value < 0 or value > 13:
                    raise InvalidValue('Invalid ramp divisor: ' + str(value))
                self.send_tmcl_command(
                    5, 153, motor_idx, value)
                self.send_tmcl_command(
                    7, 153, motor_idx, 0)  # issue a STAP command as well
            elif variable.startswith('pulsedivisor$'):
                assert isinstance(value, int)
                if value < 0 or value > 13:
                    raise InvalidValue('Invalid pulse divisor: ' + str(value))
                self.send_tmcl_command(
                    5, 154, motor_idx, value)
                self.send_tmcl_command(
                    7, 154, motor_idx, 0)  # issue a STAP command as well
            elif variable.startswith('freewheelingdelay$'):
                assert isinstance(value, int) or isinstance(value, float)
                if value < 0 or value > 65.535:
                    raise InvalidValue(
                        'Invalid freewheeling delay: ' + str(value))
                self.send_tmcl_command(
                    5, 204, motor_idx, int(value * 1000))
                self.send_tmcl_command(
                    7, 204, motor_idx, 0)  # issue a STAP command as well
            elif variable.startswith('softleft$'):
                if self.update_variable(variable, value):
                    self.save_positions()
            elif variable.startswith('softright$'):
                if self.update_variable(variable, value):
                    self.save_positions()
            elif variable in self.all_variables:
                raise ReadOnlyVariable(variable)
            else:
                raise UnknownVariable(variable)
        except TMCMConversionError:
            if not self.has_all_variables():
                # This can happen at the very beginning, re-queue the set command.
                self.inqueue.put_nowait(Message('set', 0, self.name + '__backend', name=variable, value=value))

    def save_positions(self):
        """Save the motor positions and the values of soft limits to a file.
        """
        if not self.positions_loaded.is_set():
            # avoid overwriting the position file before it can be loaded.
            self.logger.debug(
                'Not saving positions yet (process {}): file exists and up to now no complete loading happened.'.format(
                    multiprocessing.current_process().name))
            return
        # otherwise, if the positions have already been loaded once
        posfile = ''
        try:
            for mot in range(self.N_axes):
                posfile += '{:d}: {:.16f} ({:.16f}, {:.16f})\n'.format(
                    mot, self.properties['actualposition$' + str(mot)],
                    self.properties['softleft$' + str(mot)],
                    self.properties['softright$' + str(mot)])
        except KeyError as ke:
            self.logger.error(
                'Error saving motor position file for controller {} because of missing key: {}'.format(
                    self.name, ke.args[0]))
            return
        with open(os.path.join(self.configdir, self.name + '.motorpos'), 'wt',
                  encoding='utf-8') as f:
            f.write(posfile)
        self.logger.debug('Positions saved for controller ' + self.name)

    def load_positions(self):
        """Load the motor positions and the values of soft limits from a file.
        """
        self.logger.info('Loading positions for controller ' + self.name)
        if not self.busysemaphore.acquire(False):
            raise DeviceError(
                'Cannot load positions from file if controller is busy!')
        loaded = {}
        try:
            with open(os.path.join(self.configdir, self.name + '.motorpos'),
                      'rt', encoding='utf-8') as f:
                for l in f:
                    m = re.match('(?P<motoridx>\d+): (?P<position>' + RE_FLOAT +
                                 ') \((?P<leftlim>' + RE_FLOAT + '), (?P<rightlim>' + RE_FLOAT + ')\)', l)
                    if not m:
                        # since the file is broken, consider the motor
                        # positions to be set, so they can be saved later on,
                        # ensuring a good motor position file.
                        self.positions_loaded.set()
                        raise DeviceError(
                            'Invalid line in motor position file: ' + l)
                    gd = m.groupdict()
                    idx = int(gd['motoridx'])
                    loaded[idx] = {'pos': float(gd['position']),
                                   'leftlim': float(gd['leftlim']),
                                   'rightlim': float(gd['rightlim'])}

            if len(loaded) != self.N_axes:
                # since the file is broken, consider the motor
                # positions to be set, so they can be saved later on,
                # ensuring a good motor position file.
                self.positions_loaded.set()
                raise DeviceError('Invalid motor position file: ' +
                                  os.path.join(self.configdir,
                                               self.name + '.motorpos'))
            allupdated = True
            for idx in loaded:
                self.update_variable('softleft$' + str(idx), loaded[idx]['leftlim'])
                self.update_variable('softright$' + str(idx), loaded[idx]['rightlim'])
                if 'actualposition$' + str(idx) not in self.properties:
                    self.logger.warning(
                        'Actualposition for motor {:d} on controller {} not yet received. Not calibrating.'.format(
                            idx, self.name))
                    allupdated = False
                    continue
                elif abs(self.properties['actualposition$' + str(idx)] - loaded[idx]['pos']) > 0.0001:
                    self.logger.warning(
                        'Current position ({:.5f}) of motor {:d} on controller {} differs from the \
stored one ({:.5f}): calibrating to the stored value.'.format(
                            self.properties['actualposition$' + str(idx)], idx, self.name,
                            loaded[idx]['pos']))
                    self.calibrate(idx, float(loaded[idx]['pos']))
                    self.busysemaphore.acquire()
            if allupdated:
                self.logger.info('Positions loaded for controller {} in process {}'.format(
                    self.name, multiprocessing.current_process().name))
                self.positions_loaded.set()

        except FileNotFoundError:
            self.logger.info('No motor position cache file found for controller' + self.name)
            self.positions_loaded.set()
        finally:
            self.busysemaphore.release()

    def checklimits(self, motor, position):
        return (position >= self.properties['softleft$' + str(motor)]) and \
               (position <= self.properties['softright$' + str(motor)])


class TMCMCard(Device):
    backend_class = TMCMCard_Backend
    # number of motors supported by this card
    N_axes = 0
    # top RMS coil current value (Amper)
    top_RMS_current = 10000000
    # max value of microstepresolution
    max_microsteps = 6

    # internal clock frequency of the card, Hz
    clock_frequency = 16000000  # 16 MHz
    # full step is 1.8° and one complete rotation is 1 mm. Thus one full
    # step is 1/200 mm.
    full_step_size = 1 / 200.

    backend_interval = 0.5

    queryall_interval = 0.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.all_variables = DEVICE_VARIABLES + ['{}${:d}'.format(vn, motidx)
                                                 for vn, motidx in itertools.product(
                PER_MOTOR_VARIABLES, range(self.N_axes))]

        self.minimum_query_variables = self.all_variables[:]

        # self._moving: not present if no motor is moving. Otherwise a dict with the
        # following items: 'index': the index of the currently moving motor.
        # 'starttime': time of issuing the move command
        # 'startposition': RAW starting position
        # This dict belongs entirely to the backend process
        # self._moving = None

        # this flag signifies that the stored position file has been loaded
        # successfully, or did not exist when trying to load it. Until this
        # flag has been set, the position file cannot be overwritten.
        # Saving and loading motor positions (and soft limits) from the file
        # is only permitted from the backend. The frontend can only initiate
        # this via a well-crafted execute_command()
        self.positions_loaded = multiprocessing.Event()

    # noinspection PyProtectedMember
    def _get_kwargs_for_backend(self):
        d = super()._get_kwargs_for_backend()
        d['N_axes'] = self.N_axes
        d['top_RMS_current'] = self.top_RMS_current
        d['max_microsteps'] = self.max_microsteps
        d['clock_frequency'] = self.clock_frequency
        d['full_step_size'] = self.full_step_size
        d['positions_loaded'] = self.positions_loaded
        return d

    def moveto(self, motor: int, pos: float):
        """Move motor to the a given absolute (physical) position.
        """
        if not self.positions_loaded.is_set():
            raise DeviceError('Cannot move motors until positions and soft limits have been loaded')
        if not self.get_variable('_status') == 'idle':
            raise DeviceError('Can only move if the controller is idle.')
        if not self._busy.acquire(False):
            raise DeviceError('Cannot start motor movement: one motor on the controller is moving')
        self.execute_command('moveto', motor, pos)

    def moverel(self, motor, pos):
        """Move motor to a given relative (physical) position."""
        if not self.positions_loaded.is_set():
            raise DeviceError('Cannot move motors until positions and soft limits have been loaded')
        if not self.get_variable('_status') == 'idle':
            raise DeviceError('Can only move if the controller is idle.')
        if not self._busy.acquire(False):
            raise DeviceError('Cannot start motor movement: one motor on the controller is moving')
        self.execute_command('moverel', motor, pos)

    def stop(self, motor):
        """Commence stopping of a motor"""
        self.execute_command('stop', motor)

    def calibrate(self, motor, pos):
        """Calibrate the position of the motor. To be called from the FRONTEND"""
        if not self._busy.acquire(False):
            raise DeviceError('Cannot calibrate: motor controller is busy')
        self.execute_command('calibrate', motor, pos)

    def moving(self):
        """Check if any of the motors move.

        This function is callable from both the front-end and the back-end
        process. It checks `self._busysemaphore` to determine if we are moving or not."""
        return self._busy.get_value() == 0

    def checklimits(self, motor, position):
        return (position >= self._properties['softleft$' + str(motor)]) and \
               (position <= self._properties['softright$' + str(motor)])

    def set_limits(self, index, left=None, right=None):
        if left is not None:
            self.set_variable('softleft$' + str(index), left)
        if right is not None:
            self.set_variable('softright$' + str(index), right)

    def get_limits(self, index):
        return self._properties['softleft$' + str(index)], self._properties['softright$' + str(index)]

    def save_positions(self):
        self.execute_command('save_positions')

    @staticmethod
    def decode_error_flags(flags: int) -> List[str]:
        """Decode the meaning of an error bitfield.

        Should return a list of strings
        """
        raise NotImplementedError

    def where(self, motor):
        """Return the actual position of the selected motor."""
        return self.get_variable('actualposition$' + str(motor))


class TMCM351(TMCMCard):
    N_axes = 3
    top_RMS_current = 2.8
    max_microsteps = 6

    @staticmethod
    def decode_error_flags(flags: int) -> List[str]:
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


class TMCM6110(TMCMCard):
    N_axes = 6
    top_RMS_current = 1.1
    max_microsteps = 8

    @staticmethod
    def decode_error_flags(flags: int) -> List[str]:
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
