import datetime
import logging
import os

from gi.repository import GLib

from .command import Command, CommandError, CommandArgumentError
from ..devices.detector import Pilatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Trim(Command):
    """Trim the Pilatus detector

    Invocation: trim(<threshold>, <gain>)

    Arguments:
        <threshold>: the new threshold value in eV units
        <gain>: either 'lowg', 'midg' or 'highg'

    Remarks:
        None
    """
    name = 'trim'

    timeout = 20

    pulse_interval = 0.5

    required_devices = ['pilatus']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 2:
            raise CommandArgumentError('Command {} needs exactly two positional arguments.'.format(self.name))
        self.threshold = round(float(self.args[0]))
        self.gain = self.args[1].upper()
        if self.gain == 'HIGHG':
            if not ((self.threshold >= 3814) and (self.threshold <= 11614)):
                raise CommandArgumentError('Invalid threshold value for high gain: {:.2f}'.format(self.threshold))
        elif self.gain == 'MIDG':
            if not ((self.threshold >= 4425) and (self.threshold <= 14328)):
                raise CommandArgumentError('Invalid threshold value for mid gain: {:.2f}'.format(self.threshold))
        elif self.gain == 'LOWG':
            if not ((self.threshold >= 6685) and (self.threshold <= 20202)):
                raise CommandArgumentError('Invalid threshold value for low gain: {:.2f}'.format(self.threshold))
        else:
            raise CommandArgumentError('Invalid gain: ' + self.gain)

    def validate(self):
        pilatus = self.get_device('pilatus')
        assert isinstance(pilatus, Pilatus)
        if pilatus.is_busy():
            raise CommandError('Cannot start trimming if the detector is busy.')

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'threshold' and newvalue == self.threshold:
            self.cleanup(newvalue)

    def on_pulse(self):
        self.emit('pulse', 'Trimming detector')

    def execute(self):
        self.get_device('pilatus').set_threshold(self.threshold, self.gain)

    def do_return(self, retval):
        self.emit('message', 'New threshold set: {:f}. Gain: {}'.format(
            self.get_device('pilatus').get_variable('threshold'),
            self.get_device('pilatus').get_variable('gain')))
        return False

    def kill(self):
        raise CommandError('Command {} cannot be killed.'.format(self.name))


class StopExposure(Command):
    """Stop the current exposure in pilatus

    Invocation: stopexposure()

    Arguments:
        None

    Remarks:
        None
    """
    name = "stopexposure"

    required_devices = ['pilatus']

    timeout = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 2:
            raise CommandArgumentError('Command {} does not support positional arguments.'.format(self.name))

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == '_status' and newvalue == 'idle':
            self.cleanup(True)

    def execute(self):
        self.get_device('pilatus').execute_command('kill')
        self.get_device('pilatus').refresh_variable('_status')

    def kill(self):
        raise CommandError('Command {} cannot be killed.'.format(self.name))


class Expose(Command):
    """Start an exposure of a single image in pilatus

    Invocation: expose(<exptime> [, <prefix> [,<otherargs>]])

    Arguments:
        <exptime>: exposure time in seconds
        <prefix>: the prefix of the resulting file name, e.g. 'crd', 'scn', 
            'tra', 'tst', etc. If not given, it is taken from the variable
            `expose_prefix`
        <otherargs>: a dictionary, used internally, e.g. by scan.

    Returns:
        the file name returned by camserver
    """

    name = 'expose'

    pulse_interval = 0.5

    required_devices = ['pilatus']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) < 1 or len(self.args) > 3:
            raise CommandArgumentError(
                'Command {} needs at least one but not more than three positional arguments.'.format(self.name))
        self.exptime = float(self.args[0])
        if self.exptime < 1e-6 or self.exptime > 1e6:
            raise CommandArgumentError('Exposure time must be between 1e-6 and 1e6 seconds.')
        try:
            self.prefix = str(self.args[1])
        except IndexError:
            try:
                self.prefix = self.namespace['expose_prefix']
            except KeyError:
                raise CommandArgumentError(
                    'Exposure prefix must be given either as an argument to command {} or in the \'expose_prefix\' variable'.format(
                        self.name))
        try:
            assert isinstance(self.args[2], dict)
        except IndexError:
            self.otherargs = {}
        else:
            self.otherargs = self.args[2].copy()
        self.file_received = False
        self.detector_idle = False
        self.killed = False
        self.starttime = None
        self.fsn = None
        self.filename = None
        self.imgpath = None
        self.fsns = None

    def validate(self):
        det = self.get_device('pilatus')
        assert isinstance(det, Pilatus)
        if det.is_busy():
            raise CommandError('Cannot start exposing if the detector is busy.')
        if det.get_variable('nimages') != 1:
            det.set_variable('nimages', 1)

    def execute(self):
        self.fsn = self.services['filesequence'].get_nextfreefsn(self.prefix)
        self.filename = self.services['filesequence'].exposurefileformat(self.prefix, self.fsn) + '.cbf'
        det = self.get_device('pilatus')
        self.imgpath = self.config['path']['directories']['images_detector'][
                           0] + '/' + self.prefix
        if det.get_variable('imgpath') != self.imgpath:
            det.set_variable('imgpath', self.imgpath)
        # Set the exposure time. The exposure will start when the detector replies.
        det.set_variable('exptime', self.exptime)
        self.timeout = self.exptime + 30
        self.emit('message', 'Starting exposure of file: {}'.format(self.filename))
        self.starttime = None

    def on_pulse(self):
        if self.starttime is None:
            self.emit('pulse', 'Initializing...')
        else:
            spent_time = (datetime.datetime.now() - self.starttime).total_seconds()
            timeleft = self.exptime - spent_time
            self.emit('progress', 'Exposing. Remaining time: {:4.1f}'.format(timeleft), spent_time / self.exptime)
        return True

    def on_variable_change(self, device, variablename, newvalue):
        assert isinstance(device, Pilatus)
        if variablename == 'exptime':
            if self.starttime is None:
                device.expose(self.filename)
                self.starttime = datetime.datetime.now()
        elif variablename == 'starttime':
            self.starttime = newvalue
        elif variablename == 'filename':
            GLib.idle_add(lambda fsn=self.fsn, fn=newvalue, prf=self.prefix, st=self.starttime, kwargs=self.otherargs:
                          self.services['filesequence'].new_exposure(fsn, fn, prf, st, **kwargs) and False)
            self.file_received = True
        elif variablename == '_status' and newvalue == 'idle':
            self.detector_idle = True
        if (self.detector_idle and self.file_received) or self.killed:
            self.cleanup(newvalue)
        return True

    def on_error(self, device, propname, exc, tb):
        self.kill()
        return False

    def kill(self):
        self.killed = True
        self.get_device('pilatus').execute_command('kill')


class ExposeMulti(Command):
    """Start an exposure of multiple images in pilatus

    Invocation: exposemulti(<exptime>, <nimages> [, <prefix> [, <expdelay> [,<otherargs>]]])

    Arguments:
        <exptime>: exposure time in seconds
        <nimages>: the number of images expected
        <prefix>: the prefix of the resulting file name, e.g. 'crd', 'scn', 
            'tra', 'tst', etc. If not given, it is taken from the variable
            `expose_prefix`
        <expdelay>: the delay time between exposures. Defaults to 0.003 sec,
            which is the lowest allowed value.
        <otherargs>: a dictionary, used internally, e.g. by scan.

    Returns:
        the file name returned by camserver
    """

    name = 'exposemulti'

    required_devices = ['pilatus']

    pulse_interval = 0.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) < 2 or len(self.args) > 5:
            raise CommandArgumentError(
                'Command {} needs at least two but not more than five positional arguments.'.format(self.name))
        self.exptime = float(self.args[0])
        if self.exptime < 1e-6 or self.exptime > 1e6:
            raise CommandArgumentError('Exposure time must be between 1e-6 and 1e6 seconds.')
        self.nimages = int(self.args[1])
        if self.nimages < 2:
            raise CommandArgumentError('Number of images must be more than one.')
        try:
            self.prefix = str(self.args[2])
        except IndexError:
            try:
                self.prefix = self.namespace['expose_prefix']
            except KeyError:
                raise CommandArgumentError(
                    'Exposure prefix must be given either as an argument to command {} or in the \'expose_prefix\' variable'.format(
                        self.name))
        try:
            self.expdelay = float(self.args[3])
            if self.expdelay < 0.003:
                raise ValueError(self.expdelay)
        except ValueError:
            raise CommandArgumentError('Exposure delay must be a float larger than 0.003')
        except IndexError:
            self.expdelay = 0.003
        try:
            assert isinstance(self.args[4], dict)
        except IndexError:
            self.otherargs = {}
        else:
            self.otherargs = self.args[4].copy()
        self.files_received = False
        self.detector_idle = False
        self.killed = False
        self.starttime = None
        self.filechecker_handle = None
        self.fsns_done = []
        self.filenames = [self.services['filesequence'].exposurefileformat(self.prefix, f) + '.cbf'
                          for f in self.fsns]
        self.due_times = [self.exptime + i * (self.exptime + self.expdelay) for i in range(self.nimages)]
        self.totaltime = self.exptime * self.nimages + self.expdelay * (self.nimages - 1)
        self.timeout = self.totaltime + 30
        self.fsns = None
        self.imgpath = None

    def validate(self):
        det = self.get_device('pilatus')
        assert isinstance(det, Pilatus)
        if det.is_busy():
            raise CommandError('Cannot start exposing if the detector is busy.')

    def execute(self):
        dev = self.get_device('pilatus')
        assert isinstance(dev, Pilatus)
        dev.set_variable('nimages', self.nimages)
        self.fsns = list(self.services['filesequence'].get_nextfreefsns(self.prefix, self.nimages))
        dev.set_variable('expperiod', self.exptime + self.expdelay)
        self.imgpath = self.config['path']['directories']['images_detector'][
                           0] + '/' + self.prefix
        dev.set_variable('imgpath', self.imgpath)
        dev.set_variable('exptime', self.exptime)
        self.emit('message', 'Starting exposure of {:d} images. First: {}'.format(self.nimages, self.filenames[0]))

    def on_pulse(self):
        if self.starttime is None:
            self.emit('pulse', 'Initializing...')
        else:
            spent_time = (datetime.datetime.now() - self.starttime).total_seconds()
            timeleft = self.totaltime - spent_time
            self.emit('progress',
                      'Exposing {:d} images, {:d} remaining. Remaining time: {:4.1f} sec'.format(
                          self.nimages,
                          len(self.filenames), timeleft), spent_time / self.totaltime)
        return True

    def filechecker(self):
        """Periodically checks if an exposure file is available or not."""
        logger.debug('Filechecker woke.')
        if self.killed:
            return False  # unregister this idle handler
        det = self.get_device('detector')
        assert isinstance(det, Pilatus)
        assert self.starttime is not None
        # the time in seconds elapsed from issuing the "exposure" command.
        # check the times when images are due
        for filename, fsn, duetime in sorted(zip(self.filenames, self.fsns, self.due_times),
                                             key=lambda x: x[2]):
            # sorted according to duetime: we treat the next due file first.
            elapsedtime = (datetime.datetime.now() - self.starttime).total_seconds()
            if filename in self.fsns_done:
                continue
            if duetime > elapsedtime:
                continue
            if self.services['filesequence'].is_cbf_ready(self.prefix + '/' + filename):
                # if the file is present, let it be processed.
                logger.debug('We have {}'.format(filename))
                GLib.idle_add(
                    lambda fs=fsn, fn=os.path.join(self.imgpath, filename), prf=self.prefix,
                           st=self.starttime, kwargs=self.otherargs:
                    self.services['filesequence'].new_exposure(fs, fn, prf, st, **kwargs) and False)
                self.fsns_done.append(fsn)
        # no more files are expected just now
        if len(self.fsns) != len(self.fsns_done):
            # if we still have some files to wait for, re-queue us to the time when the next will be available.
            elapsedtime = (datetime.datetime.now() - self.starttime).total_seconds()
            self.filechecker_handle = GLib.timeout_add(1000 * max(0, (min(self.due_times) - elapsedtime)),
                                                       self.filechecker)
        else:
            # all files received:
            self.files_received = True
            if self.detector_idle or self.killed:
                self.cleanup(None)
        return False

    def on_variable_change(self, device, variablename, newvalue):
        assert isinstance(device, Pilatus)
        if variablename == 'exptime':
            if self.starttime is None:
                device.expose(self.filenames[0])
                self.starttime = datetime.datetime.now()
        elif variablename == 'starttime':
            if newvalue is not None:
                self.starttime = newvalue
                self.filechecker_handle = GLib.timeout_add(self.exptime * 1000, self.filechecker)
        elif variablename == '_status' and newvalue == 'idle':
            self.detector_idle = True
            if self.files_received or self.killed:
                self.cleanup(None)
        return False

    def kill(self):
        if not self.killed:
            self.killed = True
            GLib.source_remove(self.filechecker_handle)
            self.get_device('detector').execute_command('kill')

    def on_error(self, device, propname, exc, tb):
        self.kill()
        return False

    def cleanup(self, *args, **kwargs):
        if self.filechecker_handle is not None:
            GLib.source_remove(self.filechecker_handle)
            self.filechecker_handle = None
