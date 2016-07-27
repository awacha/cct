import datetime
import functools
import logging
import operator
import traceback

from .command import Command, CommandError, CommandArgumentError, CommandKilledError
from ..instrument.privileges import PRIV_BEAMSTOP, PRIV_PINHOLE, PRIV_MOVEMOTORS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Mapping(Command):
    """Do a mapping measurement

    Invocation: mapping(<motors>, <starts>, <ends>, <Npointss>,
                        <exptime> [, <exposure_prefix>])

    Arguments:
        <motors>: list of motor names (starting with the fastest increasing)
        <starts>: list of starting positions (inclusive) for the motors
        <ends>: list of end positions (inclusive) for the motors
        <Npointss>: number of points for the motors
        <exptime>: exposure time at each point
        <exposure_prefix>: exposure prefix, such as 'crd', 'tst', 'scn' etc.
            If not given, the value of the variable 'expose_prefix' will be
            used.

    Remarks:
        None
    """
    name = 'mapping'

    pulse_interval = 0.5

    motors = None  # list of motors
    starts = None  # list of start positions
    ends = None  # list of end positions
    Ns = None  # list of step numbers
    exptime = None  # exposure time at each point

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not isinstance(self.args[0], list):
            raise CommandArgumentError('Motors argument must be a list.')
        if not self.services['accounting'].has_privilege(PRIV_MOVEMOTORS):
            raise CommandError('Insufficient privileges to move motors.')
        self.motors = self.args[0]
        if len(self.motors) > len(set(self.motors)):
            raise CommandArgumentError('Each motor name must be unique in the list.')
        for m in self.motors:
            # check if the items are valid motor names
            try:
                self.get_motor(m)
            except KeyError:
                raise CommandArgumentError('Unknown motor {}'.format(m))
        self.starts = [float(x) for x in self.args[1]]
        self.ends = [float(x) for x in self.args[2]]
        self.Ns = [float(x) for x in self.args[3]]
        if len(self.starts) != len(self.motors):
            raise CommandArgumentError('Exactly the same number of start positions must be given as motors.')
        if len(self.ends) != len(self.motors):
            raise CommandArgumentError('Exactly the same number of end positions must be given as motors.')
        if len(self.Ns) != len(self.motors):
            raise CommandArgumentError('Exactly the same number of step counts must be given as motors.')
        if any([x < 2 for x in self.Ns]):
            raise CommandArgumentError('Step counts must be at least 2 in all directions.')
        self.exptime = float(self.args[4])
        if self.exptime < 1e-6 or self.exptime > 1e6:
            raise CommandArgumentError('Exposure time must be between 1e-6 and 1e6 seconds.')
        try:
            self.exposure_prefix = str(self.args[5])
        except IndexError:
            self.exposure_prefix = self.namespace['exposure_prefix']
        self.next_index = None
        self.killed = False
        self.failed = False
        self.where_index = [0] * len(self.motors)
        self.pointsdone = 0
        self.numpoints = functools.reduce(operator.mul, self.Ns, 1)
        self.moving_motor = None
        self.moving_target = None
        self.required_devices = ['xray_source', 'pilatus'] + ['Motor_' + m for m in self.motors]
        self.exposed_fsn = None
        self.exposed_filename = None
        self.exposure_starttime = None

    def validate(self):
        # check permissions for motors
        if ([m for m in self.motors if m in ['BeamStop_X', 'BeamStop_Y']] and
                not self.services['accounting'].has_privilege(PRIV_BEAMSTOP)):
            raise CommandArgumentError('Not enough privileges to move the beamstop.')
        if ([m for m in self.motors if m in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X', 'PH3_Y']] and
                not self.services['accounting'].has_privilege(PRIV_PINHOLE)):
            raise CommandArgumentError('Not enough privileges to move the pinholes.')
        # check the motor ranges
        for m, s, e in zip(self.motors, self.starts, self.ends):
            if not (self.get_motor(m).checklimits(s) and self.get_motor(m).checklimits(e)):
                raise CommandArgumentError('Range outside limits for motor {}.'.format(m))

    def execute(self):
        # move the last motor to its starting position. When the move is finished,
        # it will induce moving the previous motor to its start position, etc.
        self.moving_motor = self.motors[-1]
        self.moving_target = self.starts[-1]
        self.get_motor(self.moving_motor).moveto(self.moving_target)
        self.emit('message', 'Mapping started.')

    def on_motor_stop(self, motor, targetreached):
        assert motor.name == self.moving_motor
        if not targetreached:
            try:
                raise CommandError('Moving motor {} failed: target not reached'.format(motor.name))
            except CommandError as ce:
                self.emit('fail', ce, traceback.format_exc())
                self.failed = True
        if self.killed or self.failed:
            self.idle_return(None)
            return False
        # now move all motors in self.motors before this motor to their starting position, starting from the last
        idx = self.motors.index(self.moving_motor)
        if idx:  # avoid infinite loop from index underflow
            self.moving_motor = self.motors[idx - 1]
            self.moving_target = self.starts[idx - 1]
            self.get_motor(self.moving_motor).moveto(self.moving_target)
            return False
        # if we are here, idx was 0. This means that the very first motor has been moved to its desired position: we can start the exposure
        self.moving_motor = None
        self.moving_target = None
        self.exposed_fsn = self.services['filesequence'].get_nextfreefsn(self.exposure_prefix)
        self.exposed_filename = self.services['filesequence'].exposurefileformat(self.exposure_prefix, self.exposed_fsn)
        self.get_device('pilatus').expose(self.exposed_filename)
        self.exposure_starttime = datetime.datetime.now()

    def on_variable_change(self, device, variablename, newvalue):
        if device.name == self.get_device('detector').name and variablename == '_status' and newvalue == 'idle':
            # exposure ended.
            self.services['filesequence'].new_exposure(
                self.exposed_fsn, self.exposed_filename, self.exposure_prefix,
                self.exposure_starttime)
            self.exposure_starttime = None
            self.pointsdone += 1
            self.emit('progress', 'Mapping: {:d}/{:d} done.'.format(self.pointsdone, self.numpoints),
                      self.pointsdone / self.numpoints)
            for i in range(len(self.motors)):
                self.where_index[i] += 1
                if self.where_index[i] < self.Ns[i]:
                    self.moving_motor = self.motors[i]
                    self.moving_target = (self.ends[i] - self.starts[i]) / (self.Ns[i] - 1) * self.where_index[i] + \
                                         self.starts[i]
                    self.get_motor(self.moving_motor).moveto(self.moving_target)
                    break  # do not advance other motors
                else:
                    # if the i-th motor should not be moved further (we are at the end of the mapping range), then two
                    # cases can happen:
                    # 1) this is the last motor. When this motor reaches the end of its range, it means that the mapping
                    #     measurement is over.
                    if i == len(self.motors) - 1:
                        self.idle_return(None)
                        return False
                    # 2) otherwise the mapping must continue by stepping the next motor and resetting all the previous
                    #     motors to their start positions.
                    else:
                        # we set the where_index[i] to 0, and go on incrementing the index of the next motor. Note that
                        # whenever the next motor will move, it will ensure that this motor will move to its starting point.
                        self.where_index[i] = 0
                        # do not break, go on with the next iteration of this for loop.
        return False

    def on_pulse(self):
        if self.moving_motor is not None:
            self.emit('pulse', 'Mapping: {:d}/{:d} done. Moving motor {} to target'.format(
                self.pointsdone, self.numpoints, self.moving_motor))
        elif self.exposure_starttime is not None:
            elapsed_exptime = (datetime.datetime.now() - self.exposure_starttime).total_seconds()
            self.emit('progress', 'Mapping: {:d}/{:d} done. Exposing for {:.2f} seconds'.format(
                self.pointsdone, self.numpoints, self.exptime - elapsed_exptime),
                      (self.pointsdone * self.exptime + elapsed_exptime) / (self.numpoints * self.exptime))
        else:
            self.emit('progress', 'Mapping: {:d}/{:d} done.'.format(self.pointsdone, self.numpoints),
                      self.pointsdone / self.numpoints)

    def kill(self):
        self.killed = True
        if self.moving_motor:
            self.get_motor(self.moving_motor).stop()
            self.get_device('detector').stop()
        try:
            raise CommandKilledError
        except CommandKilledError as ce:
            self.emit('fail', ce, traceback.format_exc())
