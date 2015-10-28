from .command import Command, CommandError, CommandTimeoutError, cleanup_commandline
from .jump import JumpException, GotoException, GosubException, ReturnException
import traceback
from gi.repository import GObject, GLib

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
        self._myinterpreter=interpreter.__class__(instrument, namespace)
        self._myinterpreter_connections=[
            self._myinterpreter.connect('cmd-return', self.on_cmd_return),
            self._myinterpreter.connect('cmd-fail', self.on_cmd_fail),
            self._myinterpreter.connect('pulse', self.on_pulse),
            self._myinterpreter.connect('progress', self.on_progress),
            self._myinterpreter.connect('cmd-message', self.on_message)
        ]
        GLib.idle_add(self.nextcommand)

    def nextcommand(self):
        self._cursor+=1
        try:
            commandline=self._script[self._cursor]
        except IndexError:
            # last command, return with the result of the last command.
            self.emit('return', self._myinterpreter.command_namespace_locals['_'])
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
        except GosubException as gse:
            self._jumpstack.append(self._cursor)
            self._cursor=self.find_label(gse.args[0])
        except JumpException as je:
            raise NotImplementedError(je)
        except ScriptEndException as se:
            self.emit('return', se.args[0])
            return False
        except Exception as exc:
            self.emit('fail', exc, traceback.format_exc())
            self.emit('return', None)
        return False

    def on_cmd_return(self, myinterpreter, cmdname, returnvalue):
        if hasattr(self, '_failure'):
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
                return i
        raise ScriptError('Unknown label in script: %s'%labelname)

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
