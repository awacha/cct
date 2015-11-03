import logging
import os
import traceback

from gi.repository import GLib

from .command import Command, CommandError

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Transmission(Command):
    """Measure the transmission of a sample

    Invocation: transmission(<samplename> [, <nimages> [, <countingtime [, <emptyname>]]])

    Arguments:
        <samplename>: the name of the sample. Can also be a list of strings if
            you want to measure multiple samples at once.
        <nimages>: number of images to expose
        <countingtime>: counting time at each exposure
        <emptyname>: the sample to use for empty beam exposures

    """
    name = 'transmission'

    def execute(self, interpreter, arglist, instrument, namespace):
        self._instrument = instrument
        self._myinterpreter = interpreter.__class__(self._instrument)
        self._samplename = arglist[0]
        self._nimages = self._instrument.config['transmission']['nimages']
        self._exptime = self._instrument.config['transmission']['exptime']
        self._emptyname = self._instrument.config['transmission']['empty_sample']
        try:
            self._nimages = arglist[1]
            self._exptime = arglist[2]
            self._emptyname = arglist[3]
            self._mask = arglist[4]
        except IndexError:
            pass
        assert (self._nimages > 1)
        assert (self._exptime > 0)
        assert (self._emptyname in self._instrument.samplestore)
        if isinstance(self._samplename, str):
            self._samplename = [self._samplename]
        for sn in self._samplename:
            assert (sn in self._instrument.samplestore)

        self._exposure_prefix = instrument.config['path']['prefixes']['tra']
        self._in_fail = False
        self._kill = False
        self._myinterpreter_connections = [
            self._myinterpreter.connect(
                'cmd-return', self.on_myintr_command_return),
            self._myinterpreter.connect(
                'cmd-fail', self.on_myintr_command_fail),
            self._myinterpreter.connect('pulse', self.on_myintr_pulse),
            self._myinterpreter.connect('progress', self.on_myintr_progress),
            self._myinterpreter.connect(
                'cmd-message', self.on_myintr_command_message),
        ]
        self._instrument_connections = [
            instrument.exposureanalyzer.connect('transmdata', self.on_transmdata),
            instrument.exposureanalyzer.connect('idle', self.on_idle),
        ]
        self._intensities = []
        GLib.idle_add(lambda i=interpreter, c='start', r=None: self.on_myintr_command_return(i, c, r))
        logger.debug('Transmission measurement started')

    def on_transmdata(self, exposureanalyzer, prefix, fsn, data):
        I, what = data[0]
        if what not in self._intensities:
            self._intensities[what] = []
        self._intensities[what].append(I)

    def on_myintr_command_return(self, interpreter, commandname, returnvalue):
        try:
            if commandname == 'start':
                # check if X-ray source is in low-power mode. If no, put it there
                self._myinterpreter.execute_command('xray_power("standby")')
                return False
            elif commandname == 'xray_power':
                if returnvalue != 'Low power':
                    raise CommandError('X-ray source not in low power, cannot start scan')
                self._myinterpreter.execute_command('beamstop("out")')
                return False
            elif commandname == 'beamstop':
                if returnvalue == 'out':
                    self._myinterpreter.execute_command('exposemulti(%g, %d, "%s", 0.02, "transmdark")' %
                                                        (self._exptime, self._nimages, self._exposure_prefix))
                else:  # beamstop in
                    # this was the last command
                    self.emit('return', None)
            elif commandname == 'exposemulti':


        except Exception as exc:
            self.emit('fail', exc, traceback.format_exc())

        self._notyetstarted = False
        logger.debug('Scan subcommand %s returned' % commandname)
        if self._in_fail:
            try:
                raise CommandError('Subcommand %s failed' % commandname)
            except CommandError as ce:
                self._die(ce, traceback.format_exc())
                return False
        if self._kill:
            try:
                raise CommandError(
                    'Command %s killed in subcommand %s' % (self.name, commandname))
            except CommandError as ce:
                self._die(ce, traceback.format_exc())
                return False
        if commandname == 'moveto':
            # check if we are in the desired place
            try:
                if (not returnvalue) and (abs(self._instrument.motors[self._motor].where() - self._whereto) > 0.001):
                    raise CommandError(
                        'Positioning error: current position of motor %s (%f) is not the expected one (%f)' % (
                            self._motor, self._instrument.motors[self._motor].where(), self._whereto))
            except CommandError as ce:
                self._die(ce, traceback.format_exc())
            # we need to start the exposure
            self._myinterpreter.execute_command(
                'expose(%f, "%s", %f)' % (
                self._exptime, self._exposure_prefix, self._instrument.motors[self._motor].where()))
            self._exposureanalyzer_idle = False
        elif commandname == 'expose':
            self._idx += 1
            self.emit('progress', 'Scan running: %d/%d' % (self._idx, self._N), self._idx / self._N)
            if self._idx < self._N:
                self._whereto = self._start + self._idx * \
                                              (self._end - self._start) / (self._N - 1)
                self._myinterpreter.execute_command(
                    'moveto("%s", %f)' % (self._motor, self._whereto))
            else:
                self._scan_end = True
                if self._scan_end and self._exposureanalyzer_idle:
                    self._cleanup()
                    self.emit('return', None)
        return False

    def on_idle(self, exposureanalyzer):
        self._exposureanalyzer_idle = True
        if self._scan_end and self._exposureanalyzer_idle:
            self._cleanup()
            self.emit('return', None)

    def on_myintr_command_fail(self, interpreter, commandname, exc, failmessage):
        self.emit('fail', exc, failmessage)
        self._in_fail = True
        return False

    def on_myintr_pulse(self, interpreter, commandname, message):
        if self._notyetstarted:
            self.emit('pulse', 'Moving to start')
        return False

    def on_myintr_progress(self, interpreter, commandname, message, fraction):
        if self._notyetstarted:
            self.emit('progress', message, fraction)
        return False

    def on_myintr_command_message(self, interpreter, commandname, message):
        self.emit('message')
        return False

    def _cleanup(self):
        try:
            for c in self._myinterpreter_connections:
                self._myinterpreter.disconnect(c)
            del self._myinterpreter_connections
        except AttributeError:
            pass
        try:
            for c in self._instrument_connections:
                self._instrument.disconnect(c)
            del self._instrument_connections
        except AttributeError:
            pass

    def _die(self, exception, tback):
        self.emit('fail', exception, tback)
        self._cleanup()
        self.emit('return', None)

    def kill(self):
        self._kill = True
        self._myinterpreter.kill()


def find_in_subfolders(rootdir, target, recursive=True):
    for d in [rootdir] + find_subfolders(rootdir):
        if os.path.exists(os.path.join(d, target)):
            return os.path.join(d, target)
    raise FileNotFoundError(target)


def find_subfolders(rootdir, recursive=True):
    """Find subdirectories with a cheat: it is assumed that directory names do not
    contain periods."""
    possibledirs = [os.path.join(rootdir, x)
                    for x in sorted(os.listdir(rootdir)) if '.' not in x]
    dirs = [x for x in possibledirs if os.path.isdir(x)]
    results = dirs[:]
    if recursive:
        results = dirs[:]
        for d in dirs:
            index = results.index(d)
            for subdir in reversed(find_subfolders(d, recursive)):
                results.insert(index, subdir)
    return results
