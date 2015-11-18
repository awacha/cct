import logging
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from gi.repository import GObject, GLib

from .command import Command, CommandError, cleanup_commandline
from .jump import JumpException, GotoException, GosubException, ReturnException, PassException


class ScriptEndException(JumpException):
    pass

class ScriptError(CommandError):
    pass

class Script(Command):
    """Implement a script, i.e. a compound of commands.

    Apart from the initialization (where the text of the script has to be given), it behaves the same way as a command
    must: executed by `execute()`, which uses the same parameters; emits the same signals etc.

    Scripts can have positional arguments in a similar way as commands can. At the start of execution, the special
    variable _scriptargs is created in the namespace. Commands can reference them as _scriptargs[index] in their
    argument list.

    Subclasses can define an attribute '_cannot_return_yet': if such an attribute exists, the script does not emit the
    'return' signal, but waits (in an idle loop) for this attribute to vanish. Abnormal termination (because of an
    exception or the failure of a subcommand) does not regard this, though.

    Another useful overridable method is cleanup(): this is called before emitting the 'return' signal. It can be used
    e.g. to disconnect signal handlers.
    """

    __gsignals__={#emitted at the start of a command
                  'cmd-start':(GObject.SignalFlags.RUN_FIRST, None, (int, object,))
                  }

    script='' # a default value for the script

    def __init__(self, script=None):
        Command.__init__(self)
        if script is None:
            script=self.script
        self._script=script.split('\n')

    def execute(self, interpreter, arglist, instrument, namespace):
        namespace['_scriptargs']=arglist
        self._cursor=-1
        self._jumpstack=[]
        self._myinterpreter = interpreter.create_child(namespace)
        self._myinterpreter_connections=[
            self._myinterpreter.connect('cmd-return', self.on_cmd_return),
            self._myinterpreter.connect('cmd-fail', self.on_cmd_fail),
            self._myinterpreter.connect('pulse', self.on_pulse),
            self._myinterpreter.connect('progress', self.on_progress),
            self._myinterpreter.connect('cmd-message', self.on_message)
        ]
        GLib.idle_add(self.nextcommand)

    def nextcommand(self):
        if hasattr(self, '_kill'):
            try:
                self.cleanup()
            finally:
                self.emit('return', 'Killed')
            return False
        self._cursor+=1
        logger.debug('Executing line %d' % self._cursor)
        try:
            commandline=self._script[self._cursor]
        except IndexError:
            # last command, return with the result of the last command.
            GLib.idle_add(lambda rv=self._myinterpreter.command_namespace_locals['_']: self._try_to_return(rv))
            return False
        try:
            cmd=self._myinterpreter.execute_command(commandline)
            self.emit('cmd-start', self._cursor, cmd)
        except ReturnException:
            self._cursor=self._jumpstack.pop()
            GLib.idle_add(self.nextcommand)
            return False
        except GotoException as ge:
            self._cursor=self.find_label(ge.args[0])
            GLib.idle_add(self.nextcommand)
            return False
        except GosubException as gse:
            self._jumpstack.append(self._cursor)
            self._cursor=self.find_label(gse.args[0])
            GLib.idle_add(self.nextcommand)
            return False
        except ScriptEndException as se:
            GLib.idle_add(lambda returnvalue=se.args[0]:self._try_to_return(returnvalue))
            return False
        except PassException:
            # raised by a conditional goto/gosub command if the condition evaluated to False
            # jump to the next command.
            GLib.idle_add(lambda :self.nextcommand() and False)
            return False
        except JumpException as je:
            raise NotImplementedError(je)
        except Exception as exc:
            try:
                try:
                    self.emit('fail', exc, traceback.format_exc())
                finally:
                    self.cleanup()
            finally:
                self.emit('return', None)
        return False

    def on_cmd_return(self, myinterpreter, cmdname, returnvalue):
        if hasattr(self, '_failure'):
            try:
                self.cleanup()
            finally:
                self.emit('return',None)
            del self._failure
        else:
            GLib.idle_add(self.nextcommand)

    def on_cmd_fail(self, myinterpreter, cmdname, exc, tb):
        self._failure=True
        self.emit('fail', exc, tb)

    def on_pulse(self, myinterpreter, cmdname, pulsemessage):
        self.emit('pulse', pulsemessage)

    def on_progress(self, myinterpreter, cmdname, progressmessage, fraction):
        self.emit('progress', progressmessage, fraction)

    def on_message(self, myinterpreter, cmdname, message):
        self.emit('message', message)

    def cleanup(self):
        try:
            for c in self._myinterpreter_connections:
                self._myinterpreter.disconnect(c)
            del self._myinterpreter_connections
            del self._myinterpreter
        except AttributeError:
            pass

    def find_label(self, labelname):
        for i, line in enumerate(self._script):
            line=cleanup_commandline(line)
            if not line:
                continue
            if line.split()[0].startswith('@'+labelname):
                logger.debug('Label "%s" is on line #%d\n' % (labelname, i))
                return i
        raise ScriptError('Unknown label in script: %s'%labelname)

    def _try_to_return(self, returnvalue):
        if hasattr(self,'_cannot_return_yet'):
            self.emit('pulse', 'Waiting for finalization')
            GLib.timeout_add(100, lambda rv=returnvalue:self._try_to_return(rv))
            return False
        else:
            try:
                self.cleanup()
            finally:
                self.emit('return', returnvalue)
            return False

    def kill(self):
        self._kill = True
        self._myinterpreter.kill()

class End(Command):
    """End a script and return a value.

    Invocation: end([<returnvalue>])

    Arguments:
        <returnvalue>: optional return value. If not given, None is returned

    Remarks:
        Can only be used in scripts
    """
    name='end'

    def execute(self, interpreter, arglist, instrument, namespace):
        if not arglist:
            raise ScriptEndException(None)
        else:
            raise ScriptEndException(arglist[0])
