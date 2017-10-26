import logging

from .service import Service, ServiceError
from ..commands.command import Command, cleanup_commandline
from ..utils.callback import SignalFlags
from ..utils.timeout import SingleIdleFunction

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class InterpreterError(ServiceError):
    pass


class Interpreter(Service):
    name = 'interpreter'

    __signals__ = {
        # emitted when the command completes. Must be emitted exactly once.
        # This also must be the last signal emitted by the command.
        'cmd-return': (SignalFlags.RUN_FIRST, None, (str, object,)),
        # emitted on a failure. Can be emitted multiple times
        'cmd-fail': (SignalFlags.RUN_LAST, None, (str, object, str)),
        # just channeling the currently running command's 'detail' signal
        'cmd-detail': (SignalFlags.RUN_FIRST, None, (str, object)),
        # long running commands where the duration cannot be
        # estimated in advance, should emit this periodically (say
        # in every second)
        'pulse': (SignalFlags.RUN_FIRST, None, (str, str,)),
        # long running commands where the duration can be estimated
        # in advance, this should be emitted periodically (e.g. in
        # every second)
        'progress': (SignalFlags.RUN_FIRST, None, (str, str, float)),
        # send occasional messages to the command interpreter (to
        # be written to a terminal or logged at the INFO level.
        'cmd-message': (SignalFlags.RUN_FIRST, None, (str, str,)),
        # emitted when a flag changes. Arguments: the name and the new state of the flag.
        'flag': (SignalFlags.RUN_FIRST, None, (str, bool,)),
    }

    def __init__(self, *args, **kwargs):
        try:
            namespace = kwargs['namespace']
            del kwargs['namespace']
        except KeyError:
            namespace = None
        Service.__init__(self, *args, **kwargs)
        self._flags = []
        self.commands = {}
        for commandclass in Command.allcommands():
            self.commands[commandclass.name] = commandclass
        self.command_namespace_globals = {}
        if namespace is not None:
            self.command_namespace_locals = namespace
        else:
            self.command_namespace_locals = {'_config': self.instrument.config, '_': None}
        exec('import os', self.command_namespace_globals,
             self.command_namespace_locals)
        exec('import numpy as np', self.command_namespace_globals,
             self.command_namespace_locals)
        self._command_connections = {}
        self._parent = None
        self._command = None

    def create_child(self, namespace=None, **kwargs):
        """Create a child interpreter. Children and parents share the
        same set of flags, which are owned by the parent."""
        child = Interpreter(self.instrument, self.configdir, self.save_state(), namespace=namespace, **kwargs)
        child._parent = self
        return child

    def execute_command(self, commandline, arguments=None, kwargs={}):
        """Commences the execution of a command.

        Inputs:
            commandline: either a string (a valid command line) or an instance of cct.core.commands.Command
            arguments: if `commandline` was a string, this argument is disregarded. Otherwise it must be an
                ordered sequence (list or tuple) containing the arguments of the command."""
        if self.is_busy():
            raise InterpreterError('Interpreter is busy')
        if not isinstance(commandline, str):
            assert issubclass(commandline, Command)
            # we got a Command instance, not a string. Arguments are supplied as well
            if arguments is None:
                arguments = []
            commandclass = commandline
            self.command_namespace_locals['_commandline'] = '<none>'
        else:
            # we have to parse the command line. `arguments` is disregarded.
            commandline_cleaned = cleanup_commandline(commandline)
            if not commandline_cleaned:
                # if the command line was empty or contained only comments, ignore
                SingleIdleFunction(self.on_command_return, None, self.command_namespace_locals['_'])
                return None
            if commandline_cleaned.startswith('@'):
                # this is a definition of a label, ignore this.
                SingleIdleFunction(self.on_command_return, 'label', commandline_cleaned[1:].strip())
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
                logger.debug('Trying to split argumentstring *{}*'.format(argumentstring))
                arguments = []
                currentargument = ''
                openparens = {'(': 0, '[': 0, '{': 0, '"': 0, "'": 0}
                for i in range(len(argumentstring)):
                    if argumentstring[i] == ',' and all([x == 0 for x in openparens.values()]):
                        logger.debug('Separating comma at index ' + str(i))
                        arguments.append(currentargument)
                        currentargument = ''
                    else:
                        c = argumentstring[i]
                        currentargument += c
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
                            logger.debug('Comma in parenthesized region at index ' + str(i))
                if currentargument:
                    arguments.append(currentargument)
                arguments = [eval(a, self.command_namespace_globals,
                                  self.command_namespace_locals)
                             for a in arguments]
            else:
                arguments = []
            try:
                commandclass = self.commands[commandname]
            except KeyError:
                raise InterpreterError('Unknown command: ' + commandname)
            self.command_namespace_locals['_commandline'] = commandline_cleaned
        assert issubclass(commandclass, Command)
        logger.debug(
            'Executing command: {}. Args: {}. Kwargs: {}. Namespace: {}'.format(commandclass.name, arguments, kwargs,
                                                                                self.command_namespace_locals))
        self._command = commandclass(self, arguments, kwargs, self.command_namespace_locals)
        self._command_connections[self._command] = [
            self._command.connect('return', self.on_command_return),
            self._command.connect('fail', self.on_command_fail),
            self._command.connect('message', self.on_command_message),
            self._command.connect('pulse', self.on_command_pulse),
            self._command.connect('progress', self.on_command_progress),
            self._command.connect('detail', self.on_command_detail),
        ]
        try:
            # noinspection PyProtectedMember
            self._command._execute()
        except Exception as exc:
            logger.debug('Exception while executing command: {}'.format(exc))
            for c in self._command_connections[self._command]:
                self._command.disconnect(c)
            del self._command_connections[self._command]
            self._command = None
            logger.debug('Re-raising exception')
            raise
        self.emit('idle-changed', False)
        return self._command

    def current_command(self):
        return self._command

    def is_busy(self):
        return self._command is not None

    def on_command_return(self, command, retval):
        #        logger.debug("Command {} returned: {}".format(str(command),str(retval)))
        logger.debug('Got return value {} from command {}'.format(retval, command))
        self.command_namespace_locals['_'] = retval
        try:
            for c in self._command_connections[command]:
                command.disconnect(c)
            del self._command_connections[command]
        except KeyError:
            pass
        self._command = None
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
            logger.debug('Interpreter: killing currently running command ' + self._command.name)
            self._command.kill()
        except AttributeError:
            pass

    def set_flag(self, flagname):
        flagname = str(flagname)
        if self._parent is not None:
            return self._parent.set_flag(flagname)
        else:
            # we have no parent
            if flagname not in self._flags:
                self._flags.append(flagname)
                self.emit('flag', flagname, True)

    def clear_flag(self, flagname=None):
        flagname = str(flagname)
        if self._parent is not None:
            return self._parent.clear_flag(flagname)
        else:
            # we have no parent
            if flagname is None:
                logger.debug('Clearing all flags')
                for f in self._flags:
                    self.emit('flag', f, False)
                self._flags = []
            else:
                if flagname in self._flags:
                    self._flags = [f for f in self._flags if f != flagname]
                    logger.debug('Clearing flag {}'.format(flagname))
                    self.emit('flag', flagname, False)

    def is_flag(self, flagname):
        if self._parent is not None:
            return self._parent.is_flag(flagname)
        else:
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
                    'Mismatched parentheses at position {:d}'.format(i), i)
            parens[
                openparens[-1]] = (parens[openparens[-1]][0], parens[openparens[-1]][1], i)
            del openparens[-1]
    if openparens:
        raise ValueError('Open parentheses', openparens, parens, cmdline)
    return parens
