import logging
import traceback

from gi.repository import GLib

from .command import Command, CommandError, CommandArgumentError
from ..devices.motor import Motor
from ..instrument.privileges import PRIV_BEAMSTOP, PRIV_PINHOLE

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
        if self.motorname not in self.interpreter.instrument.motors:
            raise CommandArgumentError('Motor {} unknown.'.format(self.motorname))
        self.targetposition = float(self.args[1])
        if (self.motorname in ['BeamStop_X', 'BeamStop_Y'] and
                not self.interpreter.instrument.services['accounting'].has_privilege(PRIV_BEAMSTOP)):
            raise CommandError('Insufficient privileges to move the beamstop')
        if (self.motorname in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X', 'PH3_Y'] and
                not self.interpreter.instrument.services['accounting'].has_privilege(PRIV_PINHOLE)):
            raise CommandError('Insufficient privileges to move the pinholes')
        self.required_devices = ['Motor_' + self.motorname]

    def validate(self):
        if self.name == 'moveto':
            targetpos = self.targetposition
        elif self.name == 'moverel':
            mot = self.interpreter.instrument.motors[self.motorname]
            actpos = mot.where()
            targetpos = actpos + self.targetposition
        else:
            raise ValueError(self.name)
        if not self.interpreter.instrument.motors[self.motorname].checklimits(targetpos):
            raise CommandArgumentError('Target position for motor {} outside soft limits.'.format(self.motorname))
        return True

    def execute(self):
        motor = self.interpreter.instrument.motors[self.motorname]
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

    def execute(self, interpreter, arglist, instrument, namespace):
        if arglist:
            ret = instrument.motors[arglist[0]].where()
            txt = arglist[0] + ': {:8.3f}'.format(ret)
        else:
            ret = dict([(m, instrument.motors[m].where())
                        for m in instrument.motors])
            poslabels = {m: '{:8.3f}'.format(ret[m]) for m in ret}
            longestmotorname = max(
                max([len(m) for m in instrument.motors]), len('Motor name'))
            longestposlabel = max(len(poslabels[m]) for m in poslabels)

            heading = '| {:<{:d}} | {:<{:d}} |'.format('Motor name', longestmotorname, 'Position', longestposlabel)
            separator = '+' + '-' * (longestmotorname + 2) + '+' + '-' * (longestposlabel + 2) + '+'
            txt = '\n'.join(
                [separator, heading, separator] + ['| {:<{:d}} | {:<{:d}} |'.format(
                    m, longestmotorname, poslabels[m], longestposlabel) for m in sorted(poslabels)] + [separator])
        GLib.idle_add(lambda m=txt, r=ret: self._idlefunc(m, r))

    def _idlefunc(self, message, ret):
        self.emit('message', message)
        self.emit('return', ret)
        return False


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

    def execute(self, interpreter, arglist, instrument, namespace):
        self._instrument = instrument
        if not arglist:
            GLib.idle_add(self.end_command)
            return
        if not self._instrument.accounting.has_privilege(PRIV_BEAMSTOP):
            raise CommandError('Insufficient privileges to move beamstop')
        if isinstance(arglist[0], str):
            if (arglist[0].upper() == 'IN'):
                arglist[0] = True
            elif (arglist[0].upper() == 'OUT'):
                arglist[0] = False
            else:
                raise ValueError(arglist[0])
        elif isinstance(arglist[0], int) or isinstance(arglist[0], float) or isinstance(arglist[0], bool):
            arglist[0] = bool(arglist[0])
        else:
            raise TypeError(arglist[0])
        if arglist[0]:
            self._xpos, self._ypos = self._instrument.config['beamstop']['in']
            self._direction = 'in'
        else:
            self._xpos, self._ypos = self._instrument.config['beamstop']['out']
            self._direction = 'out'
        self._motorconnections = [self._instrument.motors['BeamStop_X'].connect('stop', self.on_stop, 'BeamStop_X'),
                                  self._instrument.motors['BeamStop_X'].connect('variable-change', self.on_varchange,
                                                                                'BeamStop_X')]
        self._startpos = self._instrument.motors['BeamStop_X'].where()
        self.emit('message', 'Moving beamstop {}.'.format(self._direction))
        self._instrument.motors['BeamStop_X'].moveto(self._xpos)

    def on_stop(self, motor, targetpositionreached, motorname):
        for c in self._motorconnections:
            motor.disconnect(c)
        del self._motorconnections
        if not targetpositionreached:
            try:
                raise CommandError(
                    'Error on moving beamstop: target position could not be reached with motor ' + motorname)
            except Exception as ce:
                self.emit('fail', (ce, traceback.format_exc()))
        if motorname == 'BeamStop_X':
            self._motorconnections = [self._instrument.motors['BeamStop_Y'].connect('stop', self.on_stop, 'BeamStop_Y'),
                                      self._instrument.motors['BeamStop_Y'].connect('variable-change',
                                                                                    self.on_varchange, 'BeamStop_Y')]
            self._startpos = self._instrument.motors['BeamStop_Y'].where()
            try:
                self._instrument.motors['BeamStop_Y'].moveto(self._ypos)
            except Exception as exc:
                self._instrument.motors['BeamStop_Y'].disconnect(self._stopconnection)
                del self._stopconnection
                self.emit('fail', exc, traceback.format_exc())
                self.emit('return', None)
        else:
            self.end_command()

    def on_varchange(self, device, variablename, newvalue, motorname):
        if variablename == 'actualposition':
            target = device.get_variable('targetposition')
            if self._startpos != target:
                self.emit('progress',
                          'Moving beamstop {}. Motor {} to {:.3f}, Now at: {:.3f}'.format(self._direction, motorname,
                                                                                          target, newvalue),
                          1 - (newvalue - target) / (self._startpos - target))

    def end_command(self):
        xpos = self._instrument.motors['BeamStop_X'].where()
        ypos = self._instrument.motors['BeamStop_Y'].where()
        if ((abs(xpos - self._instrument.config['beamstop']['in'][0]) < 0.001) and
                (abs(ypos - self._instrument.config['beamstop']['in'][1]) < 0.001)):
            self.emit('message', 'Beamstop is in the beam.')
            self.emit('return', 'in')
        elif ((abs(xpos - self._instrument.config['beamstop']['out'][0]) < 0.001) and
                  (abs(ypos - self._instrument.config['beamstop']['out'][1]) < 0.001)):
            self.emit('message', 'Beamstop is out of the beam.')
            self.emit('return', 'out')
        else:
            self.emit('message', 'Beamstop position is inconsistent.')
            self.emit('return', 'none')
        return False


class Sample(Command):
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

    def execute(self, interpreter, arglist, instrument, namespace):
        self._instrument = instrument
        if not arglist:
            GLib.idle_add(self.end_command)
            return
        self._instrument.samplestore.set_active(arglist[0])
        sample = self._instrument.samplestore.get_active()
        assert (sample.title == arglist[0])
        self._xpos = sample.positionx.val
        self._ypos = sample.positiony.val
        self._motorconnections = [self._instrument.motors['Sample_X'].connect('stop', self.on_stop, 'Sample_X'),
                                  self._instrument.motors['Sample_X'].connect('variable-change', self.on_varchange,
                                                                              'Sample_X')]
        self._startpos = self._instrument.motors['Sample_X'].where()
        self.emit('message', 'Moving sample {} into the beam.'.format(sample.title))
        logger.debug('Moving Sample_X motor to {:f}'.format(self._xpos))
        self._instrument.motors['Sample_X'].moveto(self._xpos)

    def on_stop(self, motor, targetpositionreached, motorname):
        for c in self._motorconnections:
            motor.disconnect(c)
        del self._motorconnections
        if not targetpositionreached:
            try:
                raise CommandError(
                    'Error on moving sample: target position could not be reached with motor ' + motorname)
            except Exception as ce:
                self.emit('fail', ce, traceback.format_exc())
        logger.debug('Movement ended for motor {}'.format(motorname))
        if motorname == 'Sample_X':
            self._motorconnections = [self._instrument.motors['Sample_Y'].connect('stop', self.on_stop, 'Sample_Y'),
                                      self._instrument.motors['Sample_Y'].connect('variable-change', self.on_varchange,
                                                                                  'Sample_Y')]
            self._startpos = self._instrument.motors['Sample_Y'].where()
            try:
                logger.debug('Moving Sample_Y motor to {:f}'.format(self._ypos))
                self._instrument.motors['Sample_Y'].moveto(self._ypos)
            except Exception as exc:
                try:
                    self._instrument.motors['Sample_Y'].disconnect(self._stopconnection)
                    del self._stopconnection
                except AttributeError:
                    pass
                self.emit('fail', exc, traceback.format_exc())
                self.emit('return', None)
        else:
            logger.debug('Ending command gracefully.')
            self.end_command()

    def on_varchange(self, device, variablename, newvalue, motorname):
        if variablename == 'actualposition':
            target = device.get_variable('targetposition')
            if self._startpos != target:
                self.emit('progress', 'Moving motor {} to {:.3f}. Now at: {:.3f}'.format(motorname, target, newvalue),
                          1 - (newvalue - target) / (self._startpos - target))

    def end_command(self):
        self.emit('message', 'Current sample is: ' + self._instrument.samplestore.get_active_name())
        self.emit('return', self._instrument.samplestore.get_active_name())
        return False
