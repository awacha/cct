import logging
import traceback

from gi.repository import GLib

from .command import Command, CommandError
from ..services.accounting import PrivilegeLevel

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class Moveto(Command):
    """Move motor

    Invocation: moveto(<motorname>, <position>)

    Arguments:
        <motorname>: name of the motor
        <position>: target position (physical units)

    Remarks:
        None
    """
    name = 'moveto'

    def execute(self, interpreter, arglist, instrument, namespace):
        motorname = arglist[0]
        if motorname in ['BeamStop_X', 'BeamStop_Y'] and not instrument.accounting.has_privilege(
                PrivilegeLevel.BEAMSTOP):
            raise CommandError('Insufficient privileges to move the beamstop')
        if motorname in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X',
                         'PH3_Y'] and not instrument.accounting.has_privilege(PrivilegeLevel.PINHOLE):
            raise CommandError('Insufficient privileges to move pinholes')

        position = arglist[1]

        motor = instrument.motors[motorname]
        self._connections = [motor.connect('stop', self.on_stop, motorname),
                             motor.connect(
                                 'position-change', self.on_position_change, motorname),
                             motor.connect('error', self.on_motorerror, motorname)]

        if instrument.motors[motorname].where()==position:
            GLib.idle_add(lambda m=instrument.motors[motorname],tr=True, mn=motorname:self.on_stop(m,tr,mn))
        self.emit('message', 'Moving motor %s to %.3f.' % (motorname, position))
        instrument.motors[motorname].moveto(position)

    def on_position_change(self, motor, newpos, motorname):
        self.emit('pulse', 'Moving motor %s: %-8.3f' % (motorname, newpos))

    def on_stop(self, motor, targetreached, motorname):
        try:
            for c in self._connections:
                motor.disconnect(c)
            del self._connections
        except AttributeError:
            pass
        self.emit('return', targetreached)
        return False

    def on_motorerror(self, motor, propname, exc, tb, motorname):
        self.emit('fail', exc, tb)

class Moverel(Command):
    """Move motor relatively

    Invocation: moverel(<motorname>, <position>)

    Arguments:
        <motorname>: name of the motor
        <position>: target position (physical units), relative to the present

    Remarks:
        None
    """
    name = 'moverel'

    def execute(self, interpreter, arglist, instrument, namespace):
        motorname = arglist[0]
        if motorname in ['BeamStop_X', 'BeamStop_Y'] and not instrument.accounting.has_privilege(
                PrivilegeLevel.BEAMSTOP):
            raise CommandError('Insufficient privileges to move the beamstop')
        if motorname in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X',
                         'PH3_Y'] and not instrument.accounting.has_privilege(PrivilegeLevel.PINHOLE):
            raise CommandError('Insufficient privileges to move pinholes')
        position = arglist[1]

        motor = instrument.motors[motorname]
        self._connections = [motor.connect('stop', self.on_stop, motorname),
                             motor.connect(
                                 'position-change', self.on_position_change, motorname),
                             motor.connect('error', self.on_motorerror, motorname)]
        if position==0:
            GLib.idle_add(lambda m=instrument.motors[motorname],tr=True, mn=motorname:self.on_stop(m,tr,mn))
        self.emit('message', 'Moving motor %s by %.3f.' % (motorname, position))
        instrument.motors[motorname].moverel(position)

    def on_position_change(self, motor, newpos, motorname):
        self.emit('pulse', 'Moving motor %s: %-8.2f' % (motorname, newpos))

    def on_stop(self, motor, targetreached, motorname):
        try:
            for c in self._connections:
                motor.disconnect(c)
            del self._connections
        except AttributeError:
            pass
        self.emit('return', targetreached)
        return False

    def on_motorerror(self, motor, propname, exc, tb, motorname):
        self.emit('fail', exc, tb)

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
            txt = arglist[0] + ': %8.3f' % ret
        else:
            longestmotorname = max(
                max([len(m) for m in instrument.motors]), len('Motor name'))

            heading = '| ' + \
                ('%%-%ds' % longestmotorname) % 'Motor name' + \
                ' | Position |'
            separator = '+' + '-' * (len(heading) - 2) + '+'
            ret = dict([(m, instrument.motors[m].where())
                        for m in instrument.motors])
            txt = '\n'.join(
                [separator, heading, separator] + [('| %%-%ds | %%8.3f |' % longestmotorname) % (m, ret[m]) for m in sorted(ret)] + [separator])
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
        if not self._instrument.accounting.has_privilege(PrivilegeLevel.BEAMSTOP):
            raise CommandError('Insufficient privileges to move beamstop')
        if (arglist[0] == 'in') or ((isinstance(arglist[0],int) or isinstance(arglist[0], bool) or isinstance(arglist[0],float) and bool(arglist[0]))):
            self._xpos, self._ypos = self._instrument.config['beamstop']['in']
            self._direction='in'
        elif (arglist[0] == 'out') or ((isinstance(arglist[0],int) or isinstance(arglist[0], bool) or isinstance(arglist[0],float) and not bool(arglist[0]))):
            self._xpos, self._ypos = self._instrument.config['beamstop']['out']
            self._direction='out'
        else:
            raise ConnectionError('Invalid argument: ' + str(arglist[0]))
        self._motorconnections = [self._instrument.motors['BeamStop_X'].connect('stop', self.on_stop, 'BeamStop_X'),
                                  self._instrument.motors['BeamStop_X'].connect('variable-change', self.on_varchange, 'BeamStop_X')]
        self._startpos=self._instrument.motors['BeamStop_X'].where()
        self.emit('message', 'Moving beamstop %s.' % (self._direction))
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
                                      self._instrument.motors['BeamStop_Y'].connect('variable-change', self.on_varchange, 'BeamStop_Y')]
            self._startpos=self._instrument.motors['BeamStop_Y'].where()
            try:
                self._instrument.motors['BeamStop_Y'].moveto(self._ypos)
            except Exception as exc:
                self._instrument.motors['BeamStop_Y'].disconnect(self._stopconnection)
                del self._stopconnection
                self.emit('fail',exc,traceback.format_exc())
                self.emit('return',None)
        else:
            self.end_command()

    def on_varchange(self, device, variablename, newvalue, motorname):
        if variablename=='actualposition':
            target=device.get_variable('targetposition')
            self.emit('progress', 'Moving beamstop %s. Motor %s to %.3f, Now at: %.3f'%(self._direction, motorname, target, newvalue),
                      1-(newvalue-target)/(self._startpos-target))


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
        sample=self._instrument.samplestore.get_active()
        assert (sample.title == arglist[0])
        self._xpos = sample.positionx.val
        self._ypos = sample.positiony.val
        self._motorconnections = [self._instrument.motors['Sample_X'].connect('stop', self.on_stop, 'Sample_X'),
                                  self._instrument.motors['Sample_X'].connect('variable-change', self.on_varchange, 'Sample_X')]
        self._startpos=self._instrument.motors['Sample_X'].where()
        self.emit('message', 'Moving sample %s into the beam.' % (sample.title))
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
                self.emit('fail', (ce, traceback.format_exc()))
        if motorname == 'Sample_X':
            self._motorconnections = [self._instrument.motors['Sample_Y'].connect('stop', self.on_stop, 'Sample_Y'),
                                      self._instrument.motors['Sample_Y'].connect('variable-change', self.on_varchange, 'Sample_Y')]
            self._startpos=self._instrument.motors['Sample_Y'].where()
            try:
                self._instrument.motors['Sample_Y'].moveto(self._ypos)
            except Exception as exc:
                self._instrument.motors['Sample_Y'].disconnect(self._stopconnection)
                del self._stopconnection
                self.emit('fail',exc,traceback.format_exc())
                self.emit('return',None)
        else:
            self.end_command()

    def on_varchange(self, device, variablename, newvalue, motorname):
        if variablename=='actualposition':
            target=device.get_variable('targetposition')
            self.emit('progress', 'Moving motor %s to %.3f. Now at: %.3f'%(motorname, target, newvalue),
                      1-(newvalue-target)/(self._startpos-target))

    def end_command(self):
        self.emit('message', 'Current sample is: %s' % self._instrument.samplestore.get_active_name())
        self.emit('return', self._instrument.samplestore.get_active_name())
        return False
