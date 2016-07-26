import logging
import traceback

from .command import Command, CommandError, CommandArgumentError
from ..devices.motor import Motor
from ..instrument.privileges import PRIV_BEAMSTOP, PRIV_PINHOLE
from ..services.samples import Sample

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GeneralMove(Command):
    name = '__abstract_move__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly two positional arguments.'.format(self.name))
        self.motorname = str(self.args[0])
        try:
            self.get_motor(self.motorname)
        except KeyError:
            raise CommandArgumentError('Motor {} unknown.'.format(self.motorname))
        self.targetposition = float(self.args[1])
        if (self.motorname in ['BeamStop_X', 'BeamStop_Y'] and
                not self.services['accounting'].has_privilege(PRIV_BEAMSTOP)):
            raise CommandError('Insufficient privileges to move the beamstop')
        if (self.motorname in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X', 'PH3_Y'] and
                not self.services['accounting'].has_privilege(PRIV_PINHOLE)):
            raise CommandError('Insufficient privileges to move the pinholes')
        self.required_devices = ['Motor_' + self.motorname]

    def validate(self):
        if self.name == 'moveto':
            targetpos = self.targetposition
        elif self.name == 'moverel':
            mot = self.get_motor(self.motorname)
            actpos = mot.where()
            targetpos = actpos + self.targetposition
        else:
            raise ValueError(self.name)
        if not self.get_motor(self.motorname).checklimits(targetpos):
            raise CommandArgumentError('Target position for motor {} outside soft limits.'.format(self.motorname))
        return True

    def execute(self):
        motor = self.get_motor(self.motorname)
        assert isinstance(motor, Motor)
        if self.name == 'moveto':
            if motor.where() == self.targetposition:
                self.idle_return(True)
            self.emit('message', 'Moving motor {} to {:.3f}.'.format(self.motorname, self.targetposition))
            motor.moveto(self.targetposition)
        elif self.name == 'moverel':
            if self.targetposition == 0:
                self.idle_return(True)
            self.emit('message', 'Moving motor {} by {:.3f}.'.format(self.motorname, self.targetposition))
            motor.moverel(self.targetposition)

    def on_motor_position_change(self, motor, newpos):
        self.emit('pulse', 'Moving motor {}: {:<8.3f}'.format(self.motorname, newpos))

    def on_stop(self, motor, targetreached):
        self.cleanup(targetreached)


class Moveto(GeneralMove):
    """Move motor

    Invocation: moveto(<motorname>, <position>)

    Arguments:
        <motorname>: name of the motor
        <position>: target position (physical units)

    Remarks:
        None
    """
    name = 'moveto'


class Moverel(GeneralMove):
    """Move motor relatively

    Invocation: moverel(<motorname>, <position>)

    Arguments:
        <motorname>: name of the motor
        <position>: target position (physical units), relative to the present

    Remarks:
        None
    """
    name = 'moverel'


class Where(Command):
    """Get current motor position(s)

    Invocation: where([<motorname>])

    Arguments:
        <motorname>: if given, return with the position of just this motor

    Remarks:
        None
    """

    name = 'where'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) > 1:
            raise CommandArgumentError('Command {} requires at most one positional argument.'.format(self.name))
        try:
            self.motorname = str(self.args[0])
            try:
                self.get_motor(self.motorname)
            except KeyError:
                raise CommandArgumentError('Motor {} unknown.'.format(self.motorname))
        except IndexError:
            self.motorname = None

    def execute(self):
        if self.motorname is not None:
            ret = self.get_motor(self.motorname).where()
            txt = '{}: {:8.3f}'.format(self.motorname, ret)
        else:
            ret = dict([(m, self.get_motor(1).where())
                        for m in self.instrument.motors])
            poslabels = {m: '{:8.3f}'.format(ret[m]) for m in ret}
            longestmotorname = max(
                max([len(m) for m in self.instrument.motors]), len('Motor name'))
            longestposlabel = max(len(poslabels[m]) for m in poslabels)

            heading = '| {:<{:d}} | {:<{:d}} |'.format('Motor name', longestmotorname, 'Position', longestposlabel)
            separator = '+' + '-' * (longestmotorname + 2) + '+' + '-' * (longestposlabel + 2) + '+'
            txt = '\n'.join(
                [separator, heading, separator] + ['| {:<{:d}} | {:<{:d}} |'.format(
                    m, longestmotorname, poslabels[m], longestposlabel) for m in sorted(poslabels)] + [separator])
        self.emit('message', txt)
        self.idle_return(ret)


class Beamstop(Command):
    """Query or adjust the beamstop

    Invocation:
        beamstop()           -- returns the current state ('in', 'out', 'none')
        beamstop(<value>)    -- moves the beamstop in or out

    Arguments:
        <value>: if 'in', True, 1: moves the beamstop in. If 'out', False, 0:
            moves the beamstop out

    Remarks:
        None
    """

    name = 'beamstop'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) > 1:
            raise CommandArgumentError('Command {} requires at most one positional argument.'.format(self.name))
        try:
            self.direction = self.args[0]
        except IndexError:
            self.direction = 'query'
            self.targetpos = None
            self.where = None
        else:
            if isinstance(self.direction, str):
                if self.direction.upper() in ['IN']:
                    self.direction = 'in'
                elif self.direction.upper() in ['OUT']:
                    self.direction = 'out'
                else:
                    raise CommandArgumentError(self.direction)
            else:
                if bool(self.direction):
                    self.direction = 'in'
                else:
                    self.direction = 'out'
            if not self.services['accounting'].has_privilege(PRIV_BEAMSTOP):
                raise CommandError('Not enough privileges to move beamstop.')
            self.required_devices = ['Motor_BeamStop_X', 'Motor_BeamStop_Y']
            self.targetpos = self.config['beamstop'][self.direction]
            self.where = (self.get_motor('BeamStop_X').where(),
                          self.get_motor('BeamStop_Y').where())

    def execute(self):
        if self.direction == 'query':
            xin, yin = self.config['beamstop']['in']
            xout, yout = self.config['beamstop']['out']
            xpos = self.get_motor('BeamStop_X').where()
            ypos = self.get_motor('BeamStop_Y').where()
            if abs(xin - xpos) < 0.01 and abs(yin - ypos) < 0.01:
                self.idle_return('in')
            elif abs(xout - xpos) < 0.01 and abs(yout - ypos) < 0.01:
                self.idle_return('out')
            else:
                self.idle_return('none')
            return
        self.emit('message', 'Moving beamstop {}.'.format(self.direction))
        self.get_motor('BeamStop_X').moveto(self.targetpos[0])

    def on_motor_stop(self, motor, targetreached):
        if not targetreached:
            try:
                raise CommandError(
                    'Error on moving beamstop: target position could not be reached with motor ' + motor.name)
            except Exception as ce:
                self.emit('fail', (ce, traceback.format_exc()))
                self.cleanup(None)
                return
        if motor.name == 'BeamStop_X':
            self.get_motor('BeamStop_Y').moveto(self.targetpos[1])
        else:
            self.cleanup(self.direction)

    def on_motor_position_change(self, motor, newposition):
        if motor.name.endswith('_X'):
            target = self.targetpos[0]
            start = self.where[0]
        elif motor.name.endswith('_Y'):
            target = self.targetpos[1]
            start = self.where[1]
        else:
            assert False
        self.emit('progress',
                  'Moving beamstop {}. Motor {} to {:.3f}, Now at: {:.3f}'.format(
                      self.direction, motor.name, target, newposition),
                  1 - (newposition - target) / (start - target))


class SetSample(Command):
    """Query or adjust the beamstop

    Invocation:
        sample()          -- returns the name of the currently active sample
        sample(<name>)    -- selects the a sample and moves it in the beam

    Arguments:
        <name>: a valid samplename

    Remarks:
        returns the name of the sample currently designated as active. If you
        have moved the sample motors after the last sample(<name>) command,
        this may differ from the actual sample in the beam.
    """

    name = 'sample'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) > 1:
            raise CommandArgumentError('Command {} requires at most one positional argument.'.format(self.name))
        try:
            self.sample = self.services['samplestore'].get_sample(self.args[0])
            assert isinstance(self.sample, Sample)
        except IndexError:
            self.sample = None
            self.targetpos = None
            self.where = None
        else:
            self.required_devices = ['Motor_Sample_X', 'Motor_Sample_Y']
            self.targetpos = (self.sample.positionx.val, self.sample.positiony.val)
            self.where = (self.get_motor('Sample_X').where(),
                          self.get_motor('Sample_Y').where())

    def execute(self):
        if self.sample is None:
            self.idle_return(self.services['samplestore'].get_active().title)
            return
        self.emit('message', 'Moving sample into the beam {}.'.format(self.sample.title))
        self.get_motor('Sample_X').moveto(self.targetpos[0])

    def on_motor_stop(self, motor, targetreached):
        if not targetreached:
            try:
                raise CommandError(
                    'Error on moving sample: target position could not be reached with motor ' + motor.name)
            except Exception as ce:
                self.emit('fail', (ce, traceback.format_exc()))
                self.cleanup(None)
                return
        if motor.name == 'Sample_X':
            self.get_motor('Sample_Y').moveto(self.targetpos[1])
        else:
            self.cleanup(self.sample.title)

    def on_motor_position_change(self, motor, newposition):
        if motor.name.endswith('_X'):
            target = self.targetpos[0]
            start = self.where[0]
        elif motor.name.endswith('_Y'):
            target = self.targetpos[1]
            start = self.where[1]
        else:
            assert False
        self.emit('progress',
                  'Moving sample {}. Motor {} to {:.3f}, Now at: {:.3f}'.format(
                      self.sample.title, motor.name, target, newposition),
                  1 - (newposition - target) / (start - target))
