import functools
import logging
import operator
import time
import traceback

from .command import Command, CommandError
from .detector import Expose
from .motor import Moveto
from ..instrument.privileges import PRIV_BEAMSTOP, PRIV_PINHOLE

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

    motors = None  # list of motors
    starts = None  # list of start positions
    ends = None  # list of end positions
    Ns = None  # list of step numbers
    exptime = None  # exposure time at each point

    def execute(self, interpreter, arglist, instrument, namespace):
        self.instrument = instrument
        self.myinterpreter = interpreter.__class__(instrument)
        if len(arglist) == 6:
            self.exposure_prefix = arglist[-1]
            arglist = arglist[:-1]
        else:
            try:
                self.exposure_prefix = namespace['expose_prefix']
            except KeyError:
                raise CommandError(
                    'Exposure prefix not given as an argument and the variable `expose_prefix` cannot be found.')
        self.motors, self.starts, self.ends, self.Ns, self.exptime = arglist
        if not (len(self.motors) == len(self.starts) == len(self.ends) == len(self.Ns)):
            raise CommandError('Motors, starts ends and Ns must be lists of the same length')
        if len(set(self.motors)) != len(self.motors):
            raise CommandError('Each motor name in the motors argument must be unique')
        unknown = [m_ for m_ in self.motors if m_ not in instrument.motors]
        if unknown:
            raise CommandError('Unknown motor(s): {}'.format(', '.join(unknown)))
        del unknown
        # check permissions for beamstop movements
        if any([m in ['BeamStop_X', 'BeamStop_Y'] for m in self.motors]) and not instrument.accounting.has_privilege(
                PRIV_BEAMSTOP):
            raise CommandError('Insufficient privileges to move the beamstop')
        # check permissions for pinhole movements
        if any([m in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X', 'PH3_Y'] for m in
                self.motors]) and not instrument.accounting.has_privilege(PRIV_PINHOLE):
            raise CommandError('Insufficient privileges to move pinholes')
        # check limits
        for m, s, e in zip(self.motors, self.starts, self.ends):
            if not instrument.motors[m].checklimits(s):
                raise CommandError('Start position of motor {} is out of software limits'.format(m))
            if not instrument.motors[m].checklimits(e):
                raise CommandError('End position of motor {} is out of software limits'.format(m))
        # check Ns
        if not all([n >= 2 for n in self.Ns]):
            raise CommandError('Number of steps must be more than 2 for all motors')
        if self.exptime <= 0:
            raise CommandError('Exposure time must be positive')

        self.next_index = None
        self._kill = False
        self.myinterpreter_connections = [
            self.myinterpreter.connect(
                'cmd-return', self.on_myintr_command_return),
            self.myinterpreter.connect(
                'cmd-fail', self.on_myintr_command_fail),
            self.myinterpreter.connect('pulse', self.on_myintr_progress),
            self.myinterpreter.connect('progress', self.on_myintr_progress),
            self.myinterpreter.connect(
                'cmd-message', self.on_myintr_command_message),
        ]
        self.where_index = [0] * len(self.motors)
        self.pointsdone = 0
        self.numpoints = functools.reduce(operator.mul, self.Ns, 1)
        # move the last motor to its starting position. When the move is finished,
        # it will induce moving the previous motor to its start position, etc.
        self.moving_motor = self.motors[-1]
        self.moving_target = self.starts[-1]
        self._in_fail = False
        self.myinterpreter.execute_command(Moveto(), [self.moving_motor, self.moving_target])
        self.emit('message', 'Mapping started.')

    def on_myintr_command_return(self, interpreter, commandname, returnvalue):
        if self._kill:
            self.cleanup()
            self.emit('return', None)
            return False
        if self._in_fail:
            self.cleanup()
            self.emit('return', None)
            return False
        if commandname == 'moveto':
            logger.info('Motor moved.')
            try:
                if (not returnvalue):
                    logger.warning('Positioning error: moveto command returned with False')
                    if (abs(self.instrument.motors[self.moving_motor].where() - self.moving_target) > 0.001):
                        raise CommandError(
                            'Positioning error: current position of motor {} ({:f}) is not the expected one ({:f})'.format(
                                self.moving_motor, self.instrument.motors[self.moving_motor].where(),
                                self.moving_target))
            except CommandError as ce:
                self.die(ce, traceback.format_exc())
            # now move all motors in self.motors before this motor to their starting position, starting from the last
            idx = self.motors.index(self.moving_motor)
            if idx:  # avoid infinet loop from index underflow
                self.moving_motor = self.motors[idx - 1]
                self.moving_target = self.starts[idx - 1]
                self.myinterpreter.execute_command(Moveto(), [self.moving_motor, self.moving_target])
                return False
            # if we are here, idx was 0. This means that the very first motor has been moved to its desired position: we can start the exposure
            del self.moving_motor
            del self.moving_target
            self.myinterpreter.execute_command(Expose(), [self.exptime, self.exposure_prefix])
            self.expstart = time.monotonic()

        elif commandname == 'expose':
            del self.expstart
            self.pointsdone += 1
            self.emit('progress', 'Mapping: {:d}/{:d} done.'.format(self.pointsdone, self.numpoints),
                      self.pointsdone / self.numpoints)
            for i in range(len(self.motors)):
                self.where_index[i] += 1
                if self.where_index[i] < self.Ns[i]:
                    self.moving_motor = self.motors[i]
                    self.moving_target = (self.ends[i] - self.starts[i]) / (self.Ns[i] - 1) * self.where_index[i] + \
                                         self.starts[i]
                    self.myinterpreter.execute_command(Moveto(), [self.moving_motor, self.moving_target])
                    break  # do not advance other motors
                else:
                    # if the i-th motor should not be moved further (we are at the end of the mapping range), then two
                    # cases can happen:
                    # 1) this is the last motor. When this motor reaches the end of its range, it means that the mapping
                    #     measurement is over.
                    if i == len(self.motors) - 1:
                        self.cleanup()
                        self.emit('return', None)
                        return False
                    # 2) otherwise the mapping must continue by stepping the next motor and resetting all the previous
                    #     motors to their start positions.
                    else:
                        # we set the where_index[i] to 0, and go on incrementing the index of the next motor. Note that
                        # whenever the next motor will move, it will ensure that this motor will move to its starting point.
                        self.where_index[i] = 0
                        # do not break, go on with the next iteration of this for loop.
        return False

    def on_myintr_command_fail(self, interpreter, commandname, exc, failmessage):
        self.emit('fail', exc, failmessage)
        self._in_fail = True
        return False

    def on_myintr_progress(self, interpreter, commandname, message, fraction=None):
        if hasattr(self, 'expstart'):
            elapsed_exptime = time.monotonic() - self.expstart
            self.emit('progress', 'Mapping: {:d}/{:d} done. Exposing for {:.2f} seconds'.format(
                self.pointsdone, self.numpoints, self.exptime - elapsed_exptime),
                      (self.pointsdone * self.exptime + elapsed_exptime) / (self.numpoints * self.exptime))
        elif hasattr(self, 'moving_motor'):
            self.emit('pulse', 'Mapping: {:d}/{:d} done. Moving motor {} to target'.format(
                self.pointsdone, self.numpoints, self.moving_motor))
        else:
            self.emit('progress', 'Mapping: {:d}/{:d} done.'.format(self.pointsdone, self.numpoints),
                      self.pointsdone / self.numpoints)
        return False

    def on_myintr_command_message(self, interpreter, commandname, message):
        self.emit('message', message)
        return False

    def cleanup(self):
        logger.debug('Cleaning up mapping measurement')
        try:
            for c in self.myinterpreter_connections:
                self.myinterpreter.disconnect(c)
            del self.myinterpreter_connections
        except AttributeError:
            pass

    def die(self, exception, tback):
        self.emit('fail', exception, tback)
        self.cleanup()
        self.emit('return', None)

    def kill(self):
        self._kill = True
        self.myinterpreter.kill()
