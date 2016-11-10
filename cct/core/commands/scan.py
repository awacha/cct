import datetime
import logging
import traceback

from .command import Command, CommandArgumentError, CommandError, CommandKilledError
from ..devices.device.frontend import Device
from ..instrument.privileges import PRIV_BEAMSTOP, PRIV_MOVEMOTORS, PRIV_PINHOLE

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GeneralScan(Command):
    name = '__generalscan'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert self.name in ['scan', 'scanrel']
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if self.name == 'scan':
            if len(self.args) != 6:
                raise CommandArgumentError('Command {} needs exactly six positional arguments.'.format(self.name))
        else:
            if len(self.args) != 5:
                raise CommandArgumentError('Command {} needs exactly five positional arguments.'.format(self.name))
        self.motorname = self.args[0]
        try:
            self.get_motor(self.motorname)
        except KeyError:
            raise CommandArgumentError('Unknown motor: {}'.format(self.motorname))
        if not self.services['accounting'].has_privilege(PRIV_MOVEMOTORS):
            raise CommandError('Insufficient privileges to move motors.')
        if (self.motorname in ['BeamStop_X', 'BeamStop_Y'] and
                not self.services['accounting'].has_privilege(PRIV_BEAMSTOP)):
            raise CommandError('Insufficient privileges to move the beamstop')
        if (self.motorname in ['PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X', 'PH3_Y'] and
                not self.services['accounting'].has_privilege(PRIV_PINHOLE)):
            raise CommandError('Insufficient privileges to move the pinholes')
        if self.name == 'scan':
            self.start = float(self.args[1])
            self.end = float(self.args[2])
            self.npoints = int(self.args[3])
            self.exptime = float(self.args[4])
            self.halfwidth = 0.5 * (self.end - self.start)
            self.comment = str(self.args[5])
        else:
            self.halfwidth = float(self.args[1])
            self.npoints = int(self.args[2])
            self.start = None  # to be determined just before execution
            self.end = None  # to be determined just before execution
            self.exptime = float(self.args[3])
            self.comment = str(self.args[4])
        if self.npoints < 2:
            raise CommandArgumentError('At least 2 points are required in a scan.')
        if self.exptime < 1e-6 or self.exptime > 1e6:
            raise CommandArgumentError('Exposure time must be between 1e-6 and 1e6 seconds.')
        self.idx = None
        self.scanfsn = None
        self.motorpos = None
        self.required_devices = ['pilatus', 'Motor_' + self.motorname]
        self.prefix = self.config['path']['prefixes']['scn']
        self.fsn_being_exposed = None
        self.file_being_exposed = None
        self.exposure_startdate = None
        self._ea_connection = None
        self._outstanding_scanpoints=0
        self._work_status=None
        self.killed = None

    def validate(self):
        motor = self.get_motor(self.motorname)
        if self.name == 'scanrel':
            pos = motor.where()
            self.start = pos - self.halfwidth
            self.end = pos + self.halfwidth
        else:
            assert self.name == 'scan'
        if not motor.checklimits(self.start):
            raise CommandArgumentError(
                'Start position is outside the software limits for motor {}'.format(self.motorname))
        if not motor.checklimits(self.end):
            raise CommandArgumentError(
                'Start position is outside the software limits for motor {}'.format(self.motorname))
        return True

    def on_variable_change(self, device: Device, variablename: str, newvalue):
        logger.debug('On_variable_change in scan: device {}, variable: {}, newvalue: {}, oldvalue: {}'.format(
            device.name, variablename, newvalue, device.get_variable(variablename)
        ))
        if self.killed is not None:
            if self.killed:
                logger.debug('Calling die_on_kill() from on_variable_change()')
                self.die_on_kill()
            return False
        elif device.name == 'pilatus' and variablename == '_status' and newvalue == 'idle' and self._work_status == 'Exposing':
            # exposure ready. Submit it to exposureanalyzer.
            self.motorpos = self.get_motor(self.motorname).where()
            self.services['filesequence'].new_exposure(
                self.fsn_being_exposed, self.file_being_exposed, self.prefix, self.exposure_startdate,
                position=self.motorpos, scanfsn=self.scanfsn)
            # don't wait for exposureanalyzer, move to the next point
            self.idx += 1
            self.emit('progress', 'Scan running: {:d}/{:d}'.format(self.idx, self.npoints), self.idx / self.npoints)
            if self.idx < self.npoints:
                nextpos = self.start + (self.end - self.start) / (self.npoints - 1) * self.idx
                # self.emit('message', 'Moving motor {} to {:.3f}'.format(self.motorname, nextpos))
                self._work_status='Moving'
                self.get_motor(self.motorname).moveto(nextpos)
            else:
                # Otherwise this was the last point. We wait for exposureanalyzer to finish all its jobs.
                # We will test that case in self.on_scanpoint()
                self._work_status='Finalizing'
                self.emit('message', 'Finalizing scan #{:d}.'.format(self.scanfsn))
        elif (device.name == 'pilatus') and (variablename == 'imgpath') and (
            self._work_status == 'Initializing detector'):
            self.emit('message', 'Moving motor {} to start position ({:.3f})'.format(self.motorname, self.start))
            self.get_motor(self.motorname).moveto(self.start)
            self._work_status = 'Moving'
        return False

    def on_scanpoint(self, exposureanalyzer, prefix, fsn, pos, counters):
        logger.debug('Scan command::on_scanpoint')
        self._outstanding_scanpoints -= 1
        if (self.idx >= self.npoints) and (self._outstanding_scanpoints <= 0):
            # the last scan point has been received.
            self.emit('message', 'Scan #{:d} finished.'.format(self.scanfsn))
            self.idle_return(self.scanfsn)
        return False

    def on_motor_stop(self, motor, targetreached):
        logger.debug('on_motor_stop in scan: motor {}, targetreached: {}'.format(motor.name, targetreached))
        if self._work_status != 'Moving':
            # unexpected stop message, disregard it.
            return False
        assert (motor.name == self.motorname)
        if self.killed is not None:
            if self.killed:
                logger.debug('Calling die_on_kill() from on_motor_stop()')
                self.die_on_kill()
            return False
        if not targetreached:
            try:
                raise CommandError('Target position of motor {} not reached.'.format(self.motorname))
            except CommandError as ce:
                self.emit('fail', ce, traceback.format_exc())
            self.idle_return(None)
            return False
        # otherwise start the exposure
        self.fsn_being_exposed = self.services['filesequence'].get_nextfreefsn(self.prefix)
        self.file_being_exposed = self.services['filesequence'].exposurefileformat(
            self.prefix, self.fsn_being_exposed) + '.cbf'
        self.exposure_startdate = datetime.datetime.now()
        self._work_status='Exposing'
        self.get_device('pilatus').expose(self.file_being_exposed)
        self._outstanding_scanpoints += 1

    def execute(self):
        self.idx = 0
        self.killed = None
        try:
            cmdline = self.namespace['commandline']
        except KeyError:
            cmdline = '{}("{}", {:f}, {:f}, {:d}, {:f}, "{}")'.format(
                self.name, self.motorname, self.start, self.end, self.npoints, self.exptime, self.comment)
        self.scanfsn = self.services['filesequence'].new_scan(
            cmdline, self.comment, self.exptime, self.npoints, self.motorname)
        self._ea_connection = self.services['exposureanalyzer'].connect('scanpoint',
                                                                        self.on_scanpoint)
        self.get_device('pilatus').set_variable('exptime', self.exptime)
        self.get_device('pilatus').set_variable('nimages', 1)
        self.get_device('pilatus').set_variable(
            'imgpath',
            self.config['path']['directories']['images_detector'][0] + '/' +
            self.config['path']['prefixes']['scn'])
        self._work_status = 'Initializing detector'
        self._outstanding_scanpoints=0
        self.emit('message', 'Scan #{:d} started.'.format(self.scanfsn))

    def cleanup(self, *args, **kwargs):
        if self._ea_connection is not None:
            self.services['exposureanalyzer'].disconnect(self._ea_connection)
            self._ea_connection = None
        self.services['filesequence'].scan_done(self.scanfsn)
        super().cleanup(*args, **kwargs)

    def kill(self):
        self.killed = True
        self.get_device('pilatus').stop()
        self.get_motor(self.motorname).stop()

    def die_on_kill(self):
        try:
            self.killed = False
            raise CommandKilledError(self.name)
        except CommandKilledError as cke:
            self.emit('fail', cke, traceback.format_exc())
        logger.debug('Calling idle_return(None) from die_on_kill')
        self.idle_return(None)
        logger.debug('Idle_return returned')


class Scan(GeneralScan):
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


class ScanRel(GeneralScan):
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
