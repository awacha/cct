import logging
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from gi.repository import GLib

from .command import Command, CommandError, CommandArgumentError
from .jump import JumpException, GotoException, GosubException, ReturnException, PassException
from ..utils.callback import SignalFlags


class ScriptEndException(JumpException):
    pass


class ScriptError(CommandError):
    pass


class Script(Command):
    """Implement a script, i.e. a compound of commands.

    This behaves the same way as a command must: initialized by the __init__()
    method, executed by `execute()`, emits the same signals etc. The only
    difference is that the __init__() method accepts a keyword argument:
    "script", which is the script text. All positional arguments given in
    'args' are available to the script in the namespace as the list
    '_scriptargs'.
    """

    __signals__ = {
        # emitted at the start of a subcommand. The arguments are the line
        # number and the Command instance.
        'cmd-start': (SignalFlags.RUN_FIRST, None, (int, object,)),
        # emitted after a pause request was successfully handled.
        'paused': (SignalFlags.RUN_FIRST, None, ()),
    }

    script = ''  # a default value for the script

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'script' in kwargs:
            self.script = kwargs['script']
            del kwargs['script']
        self._scriptlist = self.script.split('\n')
        self._pause = None
        self._kill = None
        self._cursor = -1
        self._jumpstack = []
        self._myinterpreter = None
        self._myinterpreter_connections = None
        self.namespace['_scriptargs'] = self.args
        self.namespace['_scriptkwargs'] = self.kwargs

    def create_subinterpreter(self):
        self._myinterpreter = self.interpreter.create_child(self.namespace)
        self._myinterpreter_connections = [
            self._myinterpreter.connect('cmd-return', self.on_cmd_return),
            self._myinterpreter.connect('cmd-fail', self.on_cmd_fail),
            self._myinterpreter.connect('pulse', self.on_cmd_pulse),
            self._myinterpreter.connect('progress', self.on_cmd_progress),
            self._myinterpreter.connect('cmd-message', self.on_cmd_message)
        ]

    def destroy_subinterpreter(self):
        try:
            for c in self._myinterpreter_connections:
                self._myinterpreter.disconnect(c)
        except AttributeError:
            pass
        finally:
            self._myinterpreter_connections = None
            self._myinterpreter = None

    def execute(self):
        self.create_subinterpreter()
        self._jumpstack = []
        self._cursor = -1
        self._pause = None
        self._kill = False
        GLib.idle_add(self.nextcommand)

    def nextcommand(self, retval=None):
        # Note that we must ensure returning False, as we are usually
        # called from either idle functions or command-return callbacks.
        if self._kill:
            # the previous command finished and self._kill is set. This means
            # that the command was interrupted. It should also have sent a
            # 'fail' signal, so we just clean up and exit.
            self.cleanup()
            self.emit('return', None)  # return.
            return False
        if self._failure:
            # Whenever a subcommand fails, it sets this attribute to True.
            # Whenever this is True, we break the execution of the script
            # and return. The 'fail' signal has already been propagated
            # to a higher level.
            self.cleanup()
            self.emit('return', None)  # return.
            return False
        if self._pause == False:
            # it could have been None as well, that is a different story
            self._pause = True
            self.emit('paused')
            return False
        # We have dealt with the special cases above. If execution reaches this
        # line, our task is to start the next command.
        self._cursor += 1
        logger.debug('Executing line {:d}'.format(self._cursor))
        try:
            commandline = self._scriptlist[self._cursor]
        except IndexError:
            # the previous was the last command, return the script with its
            # result.
            self.idle_return(retval)
            return False
        # try to execute the next command, and handle jump exceptions if
        # needed.
        try:
            cmd = self._myinterpreter.execute_command(commandline)
            self.emit('cmd-start', self._cursor, cmd)
        except ReturnException:
            # return from a gosub.
            try:
                self._cursor = self._jumpstack.pop()
            except IndexError:
                # pop from empty list
                try:
                    raise ScriptError('Jump stack underflow')
                except ScriptError as se:
                    self.emit('fail', se, traceback.format_exc())
                self.idle_return(None)
            else:
                # re-queue us
                GLib.idle_add(self.nextcommand)
            return False
        except GotoException as ge:
            # go to a label
            try:
                self._cursor = self.find_label(ge.args[0])
            except ScriptError as se:
                self.emit('fail', se, traceback.format_exc())
                self.idle_return(None)
            else:
                GLib.idle_add(self.nextcommand)
            return False
        except GosubException as gse:
            self._jumpstack.append(self._cursor)
            try:
                self._cursor = self.find_label(gse.args[0])
            except ScriptError as se:
                self.emit('fail', se, traceback.format_exc())
                self.idle_return(None)
            else:
                GLib.idle_add(self.nextcommand)
            return False
        except ScriptEndException as se:
            self.idle_return(se.args[0])
            return False
        except PassException:
            # raised by a conditional goto/gosub command if the condition evaluated to False
            # jump to the next command.
            GLib.idle_add(self.nextcommand())
            return False
        except JumpException as je:
            raise NotImplementedError(je)
        except Exception as exc:
            try:
                self.emit('fail', exc, traceback.format_exc())
            finally:
                self.idle_return(None)
        return False

    def on_cmd_return(self, myinterpreter, cmdname, returnvalue):
        # simply queue a call to self.nextcommand(). It will handle
        # all cases.
        GLib.idle_add(lambda rv=returnvalue: self.nextcommand(rv))
        return False

    def on_cmd_fail(self, myinterpreter, cmdname, exc, tb):
        # set the _failure attribute to True. self.nextcommand() will then
        # know not to start another command but exit.
        self._failure = True
        self.emit('fail', exc, tb)
        return False

    def on_cmd_pulse(self, myinterpreter, cmdname, pulsemessage):
        # pass through pulse signals
        self.emit('pulse', pulsemessage)
        return False

    def on_cmd_progress(self, myinterpreter, cmdname, progressmessage, fraction):
        # pass through progress signals
        self.emit('progress', progressmessage, fraction)
        return False

    def on_cmd_message(self, myinterpreter, cmdname, message):
        # pass through 'message' signals
        self.emit('message', message)
        return False

    def cleanup(self, *args, **kwargs):
        super().cleanup(*args, **kwargs)
        self.destroy_subinterpreter()

    def find_label(self, labelname):
        for i, line in enumerate(self._scriptlist):
            if line.strip() == '@' + labelname:
                logger.debug('Label "{}" is on line #{:d}\n'.format(labelname, i))
                return i
        raise ScriptError('Unknown label in script: {}'.format(labelname))

    def kill(self):
        self._kill = True
        self._myinterpreter.kill()

    def pause(self):
        self._pause = False

    def is_paused(self):
        return self._pause == False  # it can be None

    def resume(self):
        if self._pause is None:
            raise ScriptError('Cannot resume a script which has not been paused.')
        if self._pause:
            GLib.idle_add(self.nextcommand)
        self._pause = None


class End(Command):
    """End a script and return a value.

    Invocation: end([<returnvalue>])

    Arguments:
        <returnvalue>: optional return value. If not given, None is returned

    Remarks:
        Can only be used in scripts
    """
    name = 'end'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) > 1:
            raise CommandArgumentError('Command {} needs at most one positional argument.'.format(self.name))
        try:
            self.retval = self.args[0]
        except IndexError:
            self.retval = None

    def execute(self):
        raise ScriptEndException(self.retval)
