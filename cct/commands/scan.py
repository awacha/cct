from .command import Command, CommandError
import traceback


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

    def execute(self, interpreter, arglist, instrument, namespace):
        self._myinterpreter = interpreter.__class__(instrument)
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
        self._motor, self._start, self._end, self._N, self._exptime, self._comment = arglist
        assert(instrument.motors[self._motor].checklimits(self._start))
        assert(instrument.motors[self._motor].checklimits(self._end))
        assert(self._N >= 2)
        assert(self._exptime > 0)
        assert(self._motor in instrument.motors)
        self._idx = 0
        self._scanfsn = instrument.filesequence.get_nextfreescan()
        self._instrument = instrument
        self._exposure_prefix = instrument.config['path']['prefixes']['scn']
        self._whereto = self._start
        self._in_fail = False
        self._kill = False
        self._myinterpreter.execute_command(
            'moveto("%s", %f)' % (self._motor, self._start))

    def on_myintr_command_return(self, interpreter, commandname, returnvalue):
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
            if not returnvalue:
                try:
                    raise CommandError('Positioning error: current position of motor %s (%f) is not the expected one (%f)' % (
                        self._motor, self._instrument.motors[self._motor].where(), self._whereto))
                except CommandError as ce:
                    self._die(ce, traceback.format_exc())
            # we need to start the exposure
            self._myinterpreter.execute_command(
                'expose(%f, "%s")' % (self._exptime, self._exposure_prefix))
        elif commandname == 'expose':
            self._idx += 1
            if self._idx < self._N:
                self._whereto = self._start + self._idx * \
                    (self._end - self._start) / (self._N - 1)
                self._myinterpreter.execute_command(
                    'moveto("%s", %f)' % (self._motor, self._whereto))
            else:
                self._cleanup()
                self.emit('return', None)
        return False

    def on_myintr_command_fail(self, interpreter, commandname, exc, failmessage):
        self.emit('fail', exc, failmessage)
        self._in_fail = True
        return False

    def on_myintr_pulse(self, interpreter, commandname, message):
        self.emit('pulse', message)
        return False

    def on_myintr_progress(self, interpreter, commandname, message, fraction):
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

    def _die(self, exception, tback):
        self.emit('fail', exception, tback)
        self._cleanup()
        self.emit('return', None)

    def kill(self):
        self._kill = True
        self._myinterpreter.kill()
