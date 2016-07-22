import datetime
import logging
import traceback

from .command import Command, CommandError, CommandArgumentError, CommandKilledError
from ..instrument.privileges import PRIV_BEAMSTOP, PRIV_PINHOLE

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Scan(Command):
    """Do a scan measurement

    Invocation: scan(<motor>, <start>, <end>, <Npoints>, <exptime>, <comment>)

    Arguments:
        <motor>: name of the motor
        <start>: starting position (inclusive)
        <end>: end position (inclusive)
        <Npoints>: number of points
        <exptime>: exposure time at each point
        <comment>: description of the scan

    Remarks:
        None
    """
    name = 'scan'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 6:
            raise CommandArgumentError('Command {} needs exactly six positional arguments.'.format(self.name))

        self.motorname = self.args[0]
        if self.motorname not in self.interpreter.instrument.motors:
            raise CommandArgumentError('Unknown motor: {}'.format(self.motorname))
        if (self.motorname in ['BeamStop_X', 'BeamStop_Y'] and
                not self.interpreter.instrument.services['accounting'].has_privilege(PRIV_BEAMSTOP)):
            raise CommandError('Insufficient privileges to move the beamstop')
        if (self.motorname in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X', 'PH3_Y'] and
                not self.interpreter.instrument.services['accounting'].has_privilege(PRIV_PINHOLE)):
            raise CommandError('Insufficient privileges to move the pinholes')
        self.start = float(self.args[1])
        self.end = float(self.args[2])
        self.npoints = float(self.args[3])
        if self.npoints < 2:
            raise CommandArgumentError('At least 2 points are required in a scan.')
        self.exptime = float(self.args[4])
        if self.exptime < 1e-6 or self.exptime > 1e6:
            raise CommandArgumentError('Exposure time must be between 1e-6 and 1e6 seconds.')
        self.comment = str(self.args[5])
        self.idx = None
        self.scanfsn = None
        self.motorpos = None
        self.required_devices = ['pilatus', 'Motor_' + self.motorname]
        self.prefix = self.interpreter.instrument.config['path']['prefixes']['scn']
        self.fsn_being_exposed = None
        self.file_being_exposed = None
        self.exposure_startdate = None
        self._ea_connection = None
        self.killed = None

    def validate(self):
        motor = self.interpreter.instrument.motors[self.motorname]
        if not motor.checklimits(self.start):
            raise CommandArgumentError(
                'Start position is outside the software limits for motor {}'.format(self.motorname))
        if not motor.checklimits(self.end):
            raise CommandArgumentError(
                'Start position is outside the software limits for motor {}'.format(self.motorname))

    def on_variable_change(self, device, variablename, newvalue):
        if self.killed:
            self.die_on_kill()
            return False
        if device.name == 'pilatus' and variablename == '_status' and newvalue == 'idle':
            # exposure ready. Submit it to exposureanalyzer.
            self.interpreter.instrument.services['filesequence'].new_exposure(
                self.fsn_being_exposed, self.file_being_exposed, self.prefix, self.exposure_startdate,
                position=self.motorpos, scanfsn=self.scanfsn)
            # don't wait for exposureanalyzer, move to the next point
            self.idx += 1
            self.emit('progress', 'Scan running: {:d}/{:d}'.format(self.idx, self.npoints), self.idx / self.npoints)
            if self.idx < self.npoints:
                nextpos = self.start + (self.end - self.start) / (self.npoints - 1) * self.idx
                self.emit('message', 'Moving motor {} to {:.3f}'.format(self.motorname, nextpos))
                self.interpreter.instrument.motors[self.motorname].moveto(nextpos)
            else:
                # Otherwise this was the last point. We wait for exposureanalyzer to finish all its jobs.
                # We will test that case in self.on_scanpoint()
                self.emit('message', 'Scan #{:d} finished. Finalizing...'.format(self.scanfsn))
        return False

    def on_scanpoint(self, exposureanalyzer, prefix, fsn, pos, counters):
        if self.idx >= self.npoints:
            # the last scan point has been received.
            self.interpreter.instrument.services['filesequence'].scan_done(self.scanfsn)
            self.emit('message', 'Scan #{:d} finished.'.format(self.scanfsn))
            self.idle_return(self.scanfsn)
        return False

    def on_motor_stop(self, motor, targetreached):
        assert (motor.name == self.motorname)
        if self.killed:
            self.die_on_kill()
            return False
        if not targetreached:
            try:
                raise CommandError('Target position of motor {} not reached.'.format(self.motorname))
            except CommandError as ce:
                self.emit('fail', ce, traceback.format_exc())
            self.idle_return(None)
            return False
        self.motorpos = motor.where()
        # otherwise start the exposure
        self.fsn_being_exposed = self.interpreter.instrument.services['filesequence'].get_nextfreefsn(self.prefix)
        self.file_being_exposed = self.interpreter.instrument.services['filesequence'].exposurefileformat(
            self.prefix, self.fsn_being_exposed)
        self.exposure_startdate = datetime.datetime.now()
        self.interpreter.instrument.get_device('pilatus').expose(self.file_being_exposed)

    def execute(self):
        self.idx = 0
        self.killed = False
        try:
            cmdline = self.namespace['commandline']
        except KeyError:
            cmdline = '{}("{}", {:f}, {:f}, {:d}, {:f}, "{}")'.format(
                self.name, self.motorname, self.start, self.end, self.npoints, self.exptime, self.comment)
        self.scanfsn = self.interpreter.instrument.filesequence.new_scan(
            cmdline, self.comment, self.exptime, self.npoints, self.motorname)
        self._ea_connection = self.interpreter.instrument.services['exposureanalyzer'].connect('scanpoint',
                                                                                               self.on_scanpoint)

        self.emit('message', 'Moving motor {} to start position ({:.3f})'.format(self.motorname, self.start))
        self.interpreter.instrument.motors[self.motorname].moveto(self.start)
        self.interpreter.instrument.get_device('pilatus').set_variable('exptime', self.exptime)
        self.interpreter.instrument.get_device('pilatus').set_variable('nimages', 1)
        self.interpreter.instrument.get_device('pilatus').set_variable(
            'imgpath',
            self.interpreter.instrument.config['path']['directories']['images_detector'][0] + '/' +
            self.interpreter.instrument.config['path']['prefixes']['scn'])
        self.emit('message', 'Scan #{:d} started.'.format(self.scanfsn))

    def cleanup(self, *args, **kwargs):
        super().cleanup(*args, **kwargs)
        if self._ea_connection is not None:
            self.interpreter.instrument.services['exposureanalyzer'].disconnect(self._ea_connection)
            self._ea_connection = None

    def kill(self):
        self.killed = True
        self.interpreter.instrument.get_device('pilatus').stop()
        self.interpreter.instrument.motors[self.motorname].stop()

    def die_on_kill(self):
        try:
            raise CommandKilledError(self.name)
        except CommandKilledError as cke:
            self.emit('fail', cke, traceback.format_exc())
        self.idle_return(None)


class ScanRel(Scan):
    """Do a scan measurement relative to the current position of the motor

    Invocation: scan(<motor>, <halfwidth>, <Npoints>, <exptime>, <comment>)

    Arguments:
        <motor>: name of the motor
        <halfwidth>: half width of the scan range
        <Npoints>: number of points
        <exptime>: exposure time at each point
        <comment>: description of the scan

    Remarks:
        None
    """
    name = 'scanrel'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 5:
            raise CommandArgumentError('Command {} needs exactly five positional arguments.'.format(self.name))

        self.motorname = self.args[0]
        if self.motorname not in self.interpreter.instrument.motors:
            raise CommandArgumentError('Unknown motor: {}'.format(self.motorname))
        if (self.motorname in ['BeamStop_X', 'BeamStop_Y'] and
                not self.interpreter.instrument.services['accounting'].has_privilege(PRIV_BEAMSTOP)):
            raise CommandError('Insufficient privileges to move the beamstop')
        if (self.motorname in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X', 'PH3_Y'] and
                not self.interpreter.instrument.services['accounting'].has_privilege(PRIV_PINHOLE)):
            raise CommandError('Insufficient privileges to move the pinholes')
        self.halfwidth = float(self.args[1])
        self.npoints = float(self.args[2])
        if self.npoints < 2:
            raise CommandArgumentError('At least 2 points are required in a scan.')
        self.exptime = float(self.args[3])
        if self.exptime < 1e-6 or self.exptime > 1e6:
            raise CommandArgumentError('Exposure time must be between 1e-6 and 1e6 seconds.')
        self.comment = str(self.args[4])
        self.idx = None
        self.scanfsn = None
        self.motorpos = None
        self.required_devices = ['pilatus', 'Motor_' + self.motorname]
        self.prefix = self.interpreter.instrument.config['path']['prefixes']['scn']
        self.fsn_being_exposed = None
        self.file_being_exposed = None
        self.exposure_startdate = None
        self._ea_connection = None
        self.killed = None

    def validate(self):
        pos = self.interpreter.instrument.motors[self.motorname].where()
        self.start = pos - self.halfwidth
        self.end = pos + self.halfwidth
        super().validate()
