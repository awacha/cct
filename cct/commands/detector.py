from .command import Command
from gi.repository import GLib
import time
import datetime
import weakref


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
        assert(gain.upper() in ['HIGHG', 'LOWG', 'MIDG'])
        if gain.upper() == 'HIGHG':
            assert((thresholdvalue >= 3814) and (thresholdvalue <= 11614))
        elif gain.upper() == 'MIDG':
            assert((thresholdvalue >= 4425) and (thresholdvalue <= 14328))
        elif gain.upper() == 'LOWG':
            assert((thresholdvalue >= 6685) and (thresholdvalue <= 20202))
        self._install_timeout_handler(self.timeout)
        self._require_device(instrument, 'pilatus')
        self._check_for_variable = 'threshold'
        self._check_for_value = thresholdvalue
        self._install_pulse_handler('Trimming detector', 0.5)
        instrument.detector.set_threshold(thresholdvalue, gain)
        instrument.detector.refresh_variable('threshold')


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

    Invocation: expose(<exptime> [, <prefix>])

    Arguments:
        <exptime>: exposure time in seconds
        <prefix>: the prefix of the resulting file name, e.g. 'crd', 'scn', 
            'tra', 'tst', etc. If not given, it is taken from the variable
            `expose_prefix`

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
        assert(exptime > 0)
        try:
            self._prefix = arglist[1]
        except IndexError:
            self._prefix = namespace['expose_prefix']
        assert(instrument.detector.get_variable('nimages') == 1)
        self._fsn = instrument.filesequence.get_nextfreefsn(self._prefix)
        self._filename = self._prefix + '_' + \
            ('%%0%dd' %
             instrument.config['path']['fsndigits']) % self._fsn + '.cbf'
        instrument.detector.set_variable('exptime', exptime)
        self._exptime = exptime
        self.timeout = exptime + 3
        self._progresshandler = GLib.timeout_add(500,
                                                 lambda d=instrument.detector: self._progress(d))
        self._require_device(instrument, 'pilatus')
        self._check_for_variable = '_status'
        self._check_for_value = 'idle'
        self._install_timeout_handler(self.timeout)
        instrument.detector.expose(self._filename)
        self._alt_starttime = datetime.datetime.now()
        instrument.detector.refresh_variable('_status')
        self._instrument = instrument

    def _progress(self, detector):
        if not hasattr(self, '_starttime'):
            try:
                self._starttime = detector.get_variable('starttime')
            except KeyError:
                return True
        timeleft = self._exptime - \
            (datetime.datetime.now() - self._starttime).total_seconds()
        # timeleft=detector.get_variable('timeleft')
        self.emit('progress', 'Exposing to %s. Remaining time: %4.1f' % (
            detector.get_variable('targetfile'), timeleft), 1 - timeleft / self._exptime)
        return True

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'filename':
            self._uninstall_timeout_handler()
            self._uninstall_pulse_handler()
            self._unrequire_device()
            GLib.source_remove(self._progresshandler)
            self.emit('return', newvalue)
            if not hasattr(self, '_starttime'):
                self._starttime = self._alt_starttime
            GLib.idle_add(lambda fsn=self._fsn, fn=newvalue, prf=self._prefix, st=self._starttime:
                          self._instrument.filesequence.new_exposure(fsn, fn, prf, st) and False)
        return False

    def kill(self):
        self._instrument.detector.execute_command('kill')


class ExposeMulti(Command):
    """Start an exposure of multiple images in pilatus

    Invocation: exposemulti(<exptime>, <nimages> [, <prefix>, <expperiod>])

    Arguments:
        <exptime>: exposure time in seconds
        <nimages>: the number of images expected
        <prefix>: the prefix of the resulting file name, e.g. 'crd', 'scn', 
            'tra', 'tst', etc. If not given, it is taken from the variable
            `expose_prefix`

    Returns:
        the file name returned by camserver

    Remarks:

    """

    name = 'exposemulti'

    def execute(self, interpreter, arglist, instrument, namespace):
        raise NotImplementedError
        exptime = float(arglist[0])
        assert(exptime > 0)
        try:
            prefix = arglist[1]
        except IndexError:
            prefix = namespace['expose_prefix']
        assert(instrument.detector.get_variable('nimages') == 1)
        self._fsn = instrument.filesequence.get_nextfreefsn(prefix)
        self._filename = prefix + '_' + \
            ('%%0%dd' %
             instrument.config['path']['fsndigits']) % self._fsn + '.cbf'
        instrument.detector.set_variable('exptime', exptime)
        self._exptime = exptime
        self.timeout = exptime + 3
        self._progresshandler = GLib.timeout_add(500,
                                                 lambda d=instrument.detector: self._progress(d))
        self._require_device(instrument, 'pilatus')
        self._check_for_variable = '_status'
        self._check_for_value = 'idle'
        self._install_timeout_handler(self.timeout)
        instrument.detector.expose(self._filename)
        instrument.detector.refresh_variable('_status')
        self._instrument = instrument

    def _progress(self, detector):
        if not hasattr(self, '_starttime'):
            try:
                self._starttime = detector.get_variable('starttime')
            except KeyError:
                return True
        timeleft = self._exptime - \
            (datetime.datetime.now() - self._starttime).total_seconds()
        # timeleft=detector.get_variable('timeleft')
        self.emit('progress', 'Exposing to %s. Remaining time: %4.1f' % (
            detector.get_variable('targetfile'), timeleft), 1 - timeleft / self._exptime)
        return True

    def on_variable_change(self, device, variablename, newvalue):
        if variablename == 'filename':
            self._uninstall_timeout_handler()
            self._uninstall_pulse_handler()
            self._unrequire_device()
            GLib.source_remove(self._progresshandler)
            self.emit('return', newvalue)
            GLib.idle_add(lambda fsn=self._fsn, fn=newvalue:
                          self._instrument.filesequence.new_exposure(fsn, fn) and False)
        return False

    def kill(self):
        self._instrument.detector.execute_command('kill')
