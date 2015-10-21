from gi.repository import GObject, GLib
import logging
from .service import Service, ServiceError
from ..commands.command import Command
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class InterpreterError(ServiceError):
    pass


class Interpreter(Service):

    name = 'interpreter'

    __gsignals__ = {
        # emitted when the command completes. Must be emitted exactly once.
        # This also must be the last signal emitted by the command.
        'cmd-return': (GObject.SignalFlags.RUN_FIRST, None, (str, object,)),
        # emitted on a failure. Can be emitted multiple times
        'cmd-fail': (GObject.SignalFlags.RUN_LAST, None, (str, object, str)),
        # long running commands where the duration cannot be
        # estimated in advance, should emit this periodically (say
        # in every second)
        'pulse': (GObject.SignalFlags.RUN_FIRST, None, (str, str,)),
        # long running commands where the duration can be estimated
        # in advance, this should be emitted periodically (e.g. in
        # every second)
        'progress': (GObject.SignalFlags.RUN_FIRST, None, (str, str, float)),
        # send occasional messages to the command interpreter (to
        # be written to a terminal or logged at the INFO level.
        'cmd-message': (GObject.SignalFlags.RUN_FIRST, None, (str, str,)),
        'script-end': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self.commands = {}
        for commandclass in Command.allcommands():
            self.commands[commandclass.name] = commandclass
        self.command_namespace_globals = {}
        self.command_namespace_locals = {}
        exec('import os', self.command_namespace_globals,
             self.command_namespace_locals)
        exec('import numpy as np', self.command_namespace_globals,
             self.command_namespace_locals)
        self._command_connections = {}

    def execute_command(self, commandline):
        if hasattr(self, '_command'):
            raise InterpreterError('Interpreter is busy')

        commandline = commandline.strip()  # remove trailing whitespace
        # remove comments from command line. Comments are marked by a hash (#)
        # sign. Double hash sign is an escape for the single hash.
        commandline = commandline.replace('##', '__DoUbLeHaSh__')
        try:
            commandline = commandline[:commandline.index('#')]
        except ValueError:
            # if # is not in the commandline
            pass
        commandline.replace('__DoUbLeHaSh__', '#')
        if not commandline:
            # if the command line was empty or contained only comments, ignore
            GLib.idle_add(
                lambda cmd='empty', rv=None: self.on_command_return(cmd, rv))
            return
        # the command line must contain only one command, in the form of
        # `command(arg1, arg2, arg3 ...)`
        parpairs = get_parentheses_pairs(commandline, '(')
        argumentstring = commandline[parpairs[0][1] + 1:parpairs[0][2]].strip()
        if argumentstring:
            arguments = [eval(a, self.command_namespace_globals,
                              self.command_namespace_locals)
                         for a in argumentstring.split(',')]
        else:
            arguments = []
        commandname = commandline[:parpairs[0][1]].strip()
        try:
            command = self.commands[commandname]()
        except KeyError:
            raise InterpreterError('Unknown command: ' + commandname)
        self._command_connections[command] = [
            command.connect('return', self.on_command_return),
            command.connect('fail', self.on_command_fail),
            command.connect('message', self.on_command_message),
            command.connect('pulse', self.on_command_pulse),
            command.connect('progress', self.on_command_progress),
        ]
        try:
            command.execute(
                self, arguments, self.instrument, self.command_namespace_locals)
        except Exception:
            for c in self._command_connections[command]:
                command.disconnect(c)
            del self._command_connections[command]
            raise
        self._command = command

    def on_command_return(self, command, retval):
        logger.debug("Command %s returned:" % str(command) + str(retval))
        self.command_namespace_locals['_'] = retval
        try:
            for c in self._command_connections[command]:
                command.disconnect(c)
            del self._command_connections[command]
        except KeyError:
            pass
        try:
            del self._command
        except AttributeError:
            pass
        self.emit('cmd-return', str(command), retval)

    def on_command_fail(self, command, exc, tb):
        self.emit('cmd-fail', command.name, exc, tb)

    def on_command_message(self, command, msg):
        self.emit('cmd-message', command.name, msg)

    def on_command_progress(self, command, statusstring, fraction):
        self.emit('progress', command.name, statusstring, fraction)

    def on_command_pulse(self, command, statusstring):
        self.emit('pulse', command.name, statusstring)

    def kill(self):
        try:
            self._command.kill()
        except AttributeError:
            pass


def get_parentheses_pairs(cmdline, opening_types='([{'):
    parens = []
    openparens = []
    pair = {'(': ')', '[': ']', '{': '}', ')': '(', ']': '[', '}': '{'}
    closing_types = [pair[c] for c in opening_types]
    for i in range(len(cmdline)):
        if cmdline[i] in opening_types:
            parens.append((cmdline[i], i))
            openparens.append(len(parens) - 1)
        elif cmdline[i] in closing_types:
            if parens[openparens[-1]][0] != pair[cmdline[i]]:
                raise ValueError(
                    'Mismatched parentheses at position %d' % i, i)
            parens[
                openparens[-1]] = (parens[openparens[-1]][0], parens[openparens[-1]][1], i)
            del openparens[-1]
    if openparens:
        raise ValueError('Open parentheses', openparens, parens)
    return parens
