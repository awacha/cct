import datetime
import logging
import os

from gi.repository import GLib

from .command import Command, CommandError

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

    def execute(self, interpreter, arglist, instrument, namespace):
        thresholdvalue = round(float(arglist[0]))
        gain = arglist[1]
        if gain.upper() == 'HIGHG':
            if not ((thresholdvalue >= 3814) and (thresholdvalue <= 11614)):
                raise CommandError('Invalid threshold value for high gain: {:.2f}'.format(thresholdvalue))
        elif gain.upper() == 'MIDG':
            if not ((thresholdvalue >= 4425) and (thresholdvalue <= 14328)):
                raise CommandError('Invalid threshold value for mid gain: {:.2f}'.format(thresholdvalue))
        elif gain.upper() == 'LOWG':
            if not ((thresholdvalue >= 6685) and (thresholdvalue <= 20202)):
                raise CommandError('Invalid threshold value for low gain: {:.2f}'.format(thresholdvalue))
        else:
            raise CommandError('Unknown gain: ' + str(gain))
        self._install_timeout_handler(self.timeout)
        self._require_device(instrument, 'pilatus')
        self._check_for_variable = 'threshold'
        self._check_for_value = thresholdvalue
        self._install_pulse_handler('Trimming detector', 0.5)
        instrument.detector.set_threshold(thresholdvalue, gain)
        instrument.detector.refresh_variable('threshold')
        self._instrument = instrument

    def do_return(self, retval):
        self.emit('message', 'New threshold set: {:f}. Gain: {}'.format(
            self._instrument.detector.get_variable('threshold'),
            self._instrument.detector.get_variable('gain')))
        return False


class StopExposure(Command):
    """Stop the current exposure in pilatus

    Invocation: stopexposure()

    Arguments:
        None

    Remarks:
        None
    """
    name = "stopexposure"

    timeout = 10

    def execute(self, interpreter, arglist, instrument, namespace):
        self._install_timeout_handler(self.timeout)
        self._require_device(instrument, 'pilatus')
        self._check_for_variable = '_status'
        self._check_for_value = 'idle'
        try:
            instrument.detector.execute_command('kill')
        except:
            self._uninstall_timeout_handler()
            self._unrequire_device()
            raise
        instrument.detector.refresh_variable('_status')


class Expose(Command):
    """Start an exposure in pilatus

    Invocation: expose(<exptime> [, <prefix> [,<otherarg>]])

    Arguments:
        <exptime>: exposure time in seconds
        <prefix>: the prefix of the resulting file name, e.g. 'crd', 'scn', 
            'tra', 'tst', etc. If not given, it is taken from the variable
            `expose_prefix`
        <otherarg>: undocumented feature, used internally, e.g. by scan.

    Returns:
        the file name returned by camserver

    Remarks:
        this is the most basic exposure command. Note that the number of
        images, exposure period etc. is not touched. This means that this
        command may start a multi-image exposure, as well as a single one.
    """

    name = 'expose'

    def execute(self, interpreter, arglist, instrument, namespace):
        exptime = float(arglist[0])
        if exptime <= 0:
            raise CommandError('Exposure time must be positive')
        try:
            self._prefix = arglist[1]
        except IndexError:
            self._prefix = namespace['expose_prefix']
        try:
            self._otherarg = arglist[2]
        except IndexError:
            self._otherarg = None
        if instrument.detector.get_variable('nimages') != 1:
            instrument.detector.set_variable('nimages', 1)
        self._require_device(instrument, 'pilatus')
        self._fsn = instrument.filesequence.get_nextfreefsn(self._prefix)
        self._filename = '{prefix}_{fsn:0{ndigits:d}d}.cbf'.format(
            prefix=self._prefix, ndigits=instrument.config['path']['fsndigits'],
            fsn=self._fsn)
        instrument.detector.set_variable('imgpath', instrument.config['path']['directories']['images_detector'][
            0] + '/' + self._prefix)
        instrument.detector.set_variable('exptime', exptime)
        self._exptime = exptime
        self.timeout = exptime + 30
        self._progresshandler = GLib.timeout_add(
            500, lambda d=instrument.detector: self._progress(d))
        self._check_for_variable = '_status'
        self._check_for_value = 'idle'
        self._install_timeout_handler(self.timeout)
        self._instrument = instrument
        self._file_received = False
        self._detector_idle = False
        self.emit('message', 'Starting exposure of file: {}'.format(self._filename))

    def _progress(self, detector):
        try:
            starttime = detector.get_variable('starttime')
        except KeyError:
            return True
        if starttime is None:
            return True
        timeleft = self._exptime - \
                   (datetime.datetime.now() - starttime).total_seconds()
        self.emit('progress', 'Exposing. Remaining time: {:4.1f}'.format(timeleft), 1 - timeleft / self._exptime)
        return True

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'exptime':
            if not hasattr(self, '_alt_starttime'):
                device.expose(self._filename)
                self._alt_starttime = datetime.datetime.now()
        elif variablename == 'filename':
            if not hasattr(self, '_starttime'):
                self._starttime = self._alt_starttime

            GLib.idle_add(lambda fsn=self._fsn, fn=newvalue, prf=self._prefix, st=self._starttime, oa=self._otherarg:
                          self._instrument.filesequence.new_exposure(fsn, fn, prf, st, oa) and False)
            self._file_received = True
        elif variablename == '_status' and newvalue == 'idle':
            self._detector_idle = True
        if (self._detector_idle and self._file_received) or hasattr(self, '_kill'):
            self._uninstall_timeout_handler()
            self._uninstall_pulse_handler()
            self._unrequire_device()
            GLib.source_remove(self._progresshandler)
            self.emit('return', newvalue)
        return True

    def kill(self):
        self._kill = True
        self._instrument.detector.execute_command('kill')


class ExposeMulti(Command):
    """Start an exposure of multiple images in pilatus

    Invocation: exposemulti(<exptime>, <nimages> [, <prefix> [, <expdelay> [,<otherarg>]]])

    Arguments:
        <exptime>: exposure time in seconds
        <nimages>: the number of images expected
        <prefix>: the prefix of the resulting file name, e.g. 'crd', 'scn', 
            'tra', 'tst', etc. If not given, it is taken from the variable
            `expose_prefix`
        <expdelay>: the delay time between exposures. Defaults to 0.003 sec,
            which is the lowest allowed value.
        <otherarg>: undocumented feature, used internally, e.g. by scan.

    Returns:
        the file name returned by camserver

    Remarks:

    """

    name = 'exposemulti'

    def execute(self, interpreter, arglist, instrument, namespace):
        exptime = float(arglist[0])
        if exptime <= 0:
            raise CommandError('Exposure time must be positive')
        nimages = int(arglist[1])
        if nimages <= 0:
            raise CommandError('The number of images must be a positive integer')
        try:
            prefix = arglist[2]
        except IndexError:
            prefix = namespace['expose_prefix']
        try:
            expdelay = arglist[3]
        except IndexError:
            expdelay = 0.003
        try:
            self._otherarg = arglist[4]
        except IndexError:
            self._otherarg = None
        if expdelay <= 0.003:
            raise CommandError('The delay time between subsequent exposures must be larger than 0.003 seconds')
        instrument.detector.set_variable('nimages', nimages)
        self._require_device(instrument, 'pilatus')
        self._fsns = list(instrument.filesequence.get_nextfreefsns(prefix, nimages))
        self._prefix = prefix
        self._filenames_pending = ['{prefix}_{fsn:0{ndigits:d}d}.cbf'.format(
            prefix=prefix, ndigits=instrument.config['path']['fsndigits'], fsn=f)
                                   for f in self._fsns]
        self._expected_due_times = [exptime + i * (exptime + expdelay) for i in range(nimages)]
        self._exptime = exptime
        self._nimages = nimages
        self._totaltime = exptime * nimages + expdelay * (nimages - 1)
        self.timeout = self._totaltime + 30

        instrument.detector.set_variable('exptime', exptime)
        instrument.detector.set_variable('imgpath', instrument.config['path']['directories']['images_detector'][
            0] + '/' + self._prefix)
        instrument.detector.set_variable('expperiod', exptime + expdelay)
        self._progresshandler = GLib.timeout_add(500,
                                                 lambda d=instrument.detector: self._progress(d))
        self._install_timeout_handler(self.timeout)
        self._file_received = False
        self._detector_idle = False
        self._imgpath = instrument.detector.get_variable('imgpath')
        self.emit('message', 'Starting exposure of {:d} images. First: {}'.format(nimages, self._filenames_pending[0]))
        self._instrument = instrument
        self._file_received = False

    def _progress(self, detector):
        try:
            starttime = detector.get_variable('starttime')
        except KeyError:
            return True
        if starttime is None:
            return True
        timeleft = self._totaltime - \
                   (datetime.datetime.now() - starttime).total_seconds()
        # timeleft=detector.get_variable('timeleft')
        self.emit('progress', 'Exposing {:d} images, {:d} remaining. Remaining time: {:4.1f} sec'.format(self._nimages,
                                                                                                         len(
                                                                                                             self._expected_due_times),
                                                                                                         timeleft),
                  1 - timeleft / self._totaltime)
        return True

    def _filechecker(self):
        logger.debug('Filechecker woke.')
        if hasattr(self, '_kill'):
            return False
        try:
            starttime = self._instrument.detector.get_variable('starttime')
        except KeyError:
            return True
        if starttime is None:
            return True
        # the time in seconds elapsed from issuing the "exposure" command.
        elapsedtime = (datetime.datetime.now() - starttime).total_seconds()
        # check the times when images are due
        due_times = [dt for dt in self._expected_due_times if dt < elapsedtime]
        while due_times:
            # try to confirm the presence of all due images
            due_files = [fn for fn, dt in zip(self._filenames_pending, self._expected_due_times) if dt < elapsedtime]
            due_fsns = [fs for fs, dt in zip(self._fsns, self._expected_due_times) if dt < elapsedtime]
            loaded_count = 0  # collect the number of successfully found images
            for filename, fsn, dt in zip(due_files, due_fsns, due_times):
                if self._instrument.filesequence.is_cbf_ready(self._prefix + '/' + filename):
                    # if the file is present, let it be processed.
                    logger.debug('We have {}'.format(filename))
                    GLib.idle_add(
                        lambda fs=fsn, fn=os.path.join(self._imgpath, filename), prf=self._prefix, st=starttime,
                               oa=self._otherarg:
                        self._instrument.filesequence.new_exposure(fs, fn, prf, st, oa) and False)
                    self._filenames_pending.remove(filename)
                    self._fsns.remove(fsn)
                    self._expected_due_times.remove(dt)
                    loaded_count += 1
            if loaded_count != len(due_times):
                # if not all files were loaded, re-queue ourselves for immediate running.
                self._filechecker_handle = GLib.idle_add(self._filechecker)
                return False
            # time may have spent in the for-loop above, check if any images might have became available
            elapsedtime = (datetime.datetime.now() - starttime).total_seconds()
            due_times = [dt for dt in self._expected_due_times if dt < elapsedtime]
        # no more files are expected just now
        if self._filenames_pending:
            # if we still have some files to wait for, re-queue us to the time when the next will be available.
            elapsedtime = (datetime.datetime.now() - starttime).total_seconds()
            self._filechecker_handle = GLib.timeout_add(1000 * (self._expected_due_times[0] - elapsedtime),
                                                        self._filechecker)
        else:
            # all files received:
            self._file_received = True
            self._try_to_end()
        return False

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'exptime':
            if not hasattr(self, '_alt_starttime'):
                device.expose(self._filenames_pending[0])
                self._alt_starttime = datetime.datetime.now()
        elif variablename == 'starttime':
            if newvalue is not None:
                self._filechecker_handle = GLib.timeout_add(self._exptime * 1000, self._filechecker)
        elif variablename == '_status' and newvalue == 'idle':
            self._detector_idle = True
        self._try_to_end()
        return False

    def _try_to_end(self):
        if (self._file_received and self._detector_idle) or hasattr(self, '_kill'):
            self._uninstall_timeout_handler()
            self._uninstall_pulse_handler()
            self._unrequire_device()
            GLib.source_remove(self._progresshandler)
            self.emit('return', None)
            self._detector_idle = False
            self._file_received = False

    def kill(self):
        GLib.source_remove(self._filechecker_handle)
        self._kill = True
        self._instrument.detector.execute_command('kill')

    def on_error(self, device, propname, exc, tb):
        self.kill()
        return False
