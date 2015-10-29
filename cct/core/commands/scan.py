from .command import Command, CommandError
import traceback
import os
import logging
import time
logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
            instrument.exposureanalyzer.connect('scanpoint', self.on_scanpoint),
            instrument.exposureanalyzer.connect('idle', self.on_idle),
        ]
        self._scanfilename=os.path.join(self._instrument.config['path']['directories']['scan'],
                                        self._instrument.config['scan']['scanfile'])
        with open(self._scanfilename, 'at', encoding='utf-8') as f:
            f.write('\n#S %d  scan("%s", %f, %f, %d, %f, "%s")\n'%(self._scanfsn,self._motor, self._start, self._end, self._N, self._exptime, self._comment))
            f.write('#D %s\n'%time.asctime())
            f.write('#C %s\n'%self._comment)
            f.write('#T %f  (Seconds)\n'%self._exptime)
            f.write('#G0 0\n')
            f.write('#G1 0\n')
            f.write('#Q 0 0 0')
            entry_index=8
            p_index=-1
            for m in sorted(self._instrument.motors):
                if entry_index>=8:
                    p_index+=1
                    f.write('\n#P%d'%p_index)
                    entry_index=0
                f.write(' %f'%self._instrument.motors[m].where())
                entry_index+=1
            f.write('\n#N %d\n'%self._N)
            f.write('#L '+'  '.join([self._motor]+self._instrument.config['scan']['columns'])+'\n')
        try:
            self._notyetstarted=True
            self._scan_end=False
            self._myinterpreter.execute_command(
                'moveto("%s", %f)' % (self._motor, self._start))
        except Exception:
            self._cleanup()
            raise
        logger.debug('Scan command started')

    def on_scanpoint(self, exposureanalyzer, prefix, fsn, scandata):
        line=str(scandata)[0]+'  '+' '.join(str(f) for f in scandata[1:])
        with open(self._scanfilename,'at', encoding='utf-8') as f:
            f.write(line+'\n')
        self.emit('message',line)

    def on_myintr_command_return(self, interpreter, commandname, returnvalue):
        self._notyetstarted=False
        logger.debug('Scan subcommand %s returned'%commandname)
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
                if (not returnvalue) and (abs(self._instrument.motors[self._motor].where()-self._whereto)>0.001):
                    raise CommandError('Positioning error: current position of motor %s (%f) is not the expected one (%f)' % (
                        self._motor, self._instrument.motors[self._motor].where(), self._whereto))
            except CommandError as ce:
                self._die(ce, traceback.format_exc())
            # we need to start the exposure
            self._myinterpreter.execute_command(
                'expose(%f, "%s", %f)' % (self._exptime, self._exposure_prefix, self._instrument.motors[self._motor].where()))
            self._exposureanalyzer_idle=False
        elif commandname == 'expose':
            self._idx += 1
            self.emit('progress','Scan running: %d/%d'%(self._idx,self._N),self._idx/self._N)
            if self._idx < self._N:
                self._whereto = self._start + self._idx * \
                    (self._end - self._start) / (self._N - 1)
                self._myinterpreter.execute_command(
                    'moveto("%s", %f)' % (self._motor, self._whereto))
            else:
                self._scan_end=True
                if self._scan_end and self._exposureanalyzer_idle:
                    self._cleanup()
                    self.emit('return', None)
        return False

    def on_idle(self, exposureanalyzer):
        self._exposureanalyzer_idle=True
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
