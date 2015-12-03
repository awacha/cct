import logging

from gi.repository import GObject, GLib

from .service import Service, ServiceError
from ..commands.command import Command, cleanup_commandline

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
        # just channeling the currently running command's 'detail' signal
        'cmd-detail': (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
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
        # emitted when work started (False) or work finished (True).
        'idle-changed': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self, instrument, namespace=None, **kwargs):
        Service.__init__(self, instrument, **kwargs)
        self._flags = []
        self.commands = {}
        for commandclass in Command.allcommands():
            self.commands[commandclass.name] = commandclass
        self.command_namespace_globals = {}
        if namespace is not None:
            self.command_namespace_locals=namespace
        else:
            self.command_namespace_locals = {'_config': instrument.config, '_':None}
        exec('import os', self.command_namespace_globals,
             self.command_namespace_locals)
        exec('import numpy as np', self.command_namespace_globals,
             self.command_namespace_locals)
        self._command_connections = {}

    def create_child(self, namespace=None, **kwargs):
        """Create a child interpreter. Children and parents share the same set of flags."""
        child = Interpreter(self.instrument, namespace, **kwargs)
        child._parent = self
        return child

    def execute_command(self, commandline, arguments=None):
        if hasattr(self, '_command'):
            raise InterpreterError('Interpreter is busy')
        if isinstance(commandline, Command):
            # we got a Command instance, not a string. Arguments are supplied as well
            if arguments is None:
                arguments=[]
            command=commandline
            self.command_namespace_locals['_commandline'] = '<none>'
        elif isinstance(commandline, str):
            # we have to parse the command line. `arguments` is disregarded.
            commandline_cleaned=cleanup_commandline(commandline)
            if not commandline_cleaned:
                # if the command line was empty or contained only comments, ignore
                GLib.idle_add(
                    lambda cmd='empty', rv=self.command_namespace_locals['_']: self.on_command_return(cmd, rv))
                return None
            if commandline_cleaned.startswith('@'):
                # this is a definition of a label, ignore this.
                GLib.idle_add(lambda cmd='label', rv=commandline_cleaned[1:].strip(): self.on_command_return(cmd, rv))
                return None
            # the command line must contain only one command, in the form of
            # `command(arg1, arg2, arg3 ...)`
            parpairs = get_parentheses_pairs(commandline_cleaned, '(')
            if not parpairs:
                # no parentheses, can be used for commands which do not accept any arguments
                argumentstring = ''
                commandname = commandline_cleaned
            else:
                commandname = commandline_cleaned[:parpairs[0][1]].strip()
                argumentstring = commandline_cleaned[parpairs[0][1] + 1:parpairs[0][2]].strip()
            if argumentstring:
                # split the argument string at commas. Beware that arguments can be valid
                # Python expressions, thus may contain commas in various kinds of
                # parentheses, brackets, curly brackets, strings etc. Skip these.
                logger.debug('Trying to split argumentstring *%s*' % argumentstring)
                arguments = []
                currentargument = ''
                openparens = {'(': 0, '[': 0, '{': 0, '"': 0, "'": 0}
                for i in range(len(argumentstring)):
                    if argumentstring[i] == ',' and all([x == 0 for x in openparens.values()]):
                        logger.debug('Separating comma at index %d' % i)
                        arguments.append(currentargument)
                        currentargument = ''
                    else:
                        c = argumentstring[i]
                        currentargument = currentargument + c
                        if c == '(':
                            openparens['('] += 1
                        elif c == ')':
                            openparens['('] -= 1
                        elif c == '[':
                            openparens['['] += 1
                        elif c == ']':
                            openparens['['] -= 1
                        elif c == '{':
                            openparens['{'] += 1
                        elif c == '}':
                            openparens['{'] -= 1
                        elif c == '"':
                            openparens['"'] = 1 - openparens['"']
                        elif c == "'":
                            openparens["'"] = 1 - openparens["'"]
                        elif c == ',':
                            logger.debug('Comma in parenthesized region at index %d' % i)
                if currentargument:
                    arguments.append(currentargument)
                arguments = [eval(a, self.command_namespace_globals,
                                  self.command_namespace_locals)
                             for a in arguments]
            else:
                arguments = []
            try:
                command = self.commands[commandname]()
            except KeyError:
                raise InterpreterError('Unknown command: ' + commandname)
            self.command_namespace_locals['_commandline'] = commandline_cleaned
        else:
            raise NotImplementedError(commandline)
        self._command_connections[command] = [
            command.connect('return', self.on_command_return),
            command.connect('fail', self.on_command_fail),
            command.connect('message', self.on_command_message),
            command.connect('pulse', self.on_command_pulse),
            command.connect('progress', self.on_command_progress),
            command.connect('detail', self.on_command_detail),
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
        self.emit('idle-changed', False)
        return self._command

    def is_busy(self):
        return hasattr(self, '_command')

    def on_command_return(self, command, retval):
        #        logger.debug("Command %s returned:" % str(command) + str(retval))
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
        self.emit('idle-changed', True)

    def on_command_fail(self, command, exc, tb):
        self.emit('cmd-fail', command.name, exc, tb)

    def on_command_message(self, command, msg):
        self.emit('cmd-message', command.name, msg)

    def on_command_progress(self, command, statusstring, fraction):
        self.emit('progress', command.name, statusstring, fraction)

    def on_command_pulse(self, command, statusstring):
        self.emit('pulse', command.name, statusstring)

    def on_command_detail(self, command, detail):
        self.emit('cmd-detail', command.name, detail)

    def kill(self):
        try:
            logger.debug('Interpreter: killing currently running command %s' % self._command.name)
            self._command.kill()
        except AttributeError:
            pass

    def set_flag(self, flagname):
        try:
            return self._parent.set_flag(flagname)
        except AttributeError:
            # we have no parent
            if flagname not in self._flags:
                self._flags.append(flagname)

    def clear_flag(self, flagname=None):
        try:
            return self._parent.clear_flag(flagname)
        except AttributeError:
            # we have no parent
            if flagname is None:
                self._flags = []
            else:
                self._flags = [f for f in self._flags if f != flagname]

    def is_flag(self, flagname):
        try:
            return self._parent.is_flag(flagname)
        except AttributeError:
            # we have no parent
            return flagname in self._flags


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
        raise ValueError('Open parentheses', openparens, parens, cmdline)
    return parens

