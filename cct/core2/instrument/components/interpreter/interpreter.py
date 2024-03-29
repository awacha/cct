import logging
import re
from typing import Any, Dict, List, Optional
import traceback

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from .flags import InterpreterFlags
from ..component import Component
from ....commands import Command, Comment, Label

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ParsingError(Exception):
    pass


class Interpreter(QtCore.QObject, Component):
    script: List[Command] = None
    namespace: Dict[str, Any] = None
    pointer: Optional[int] = None  # points to the current command
    callstack: List[int] = None
    flags: InterpreterFlags
    stopping: Optional[bool] = None

    scriptstarted = Signal()
    message = Signal(str)
    progress = Signal(str, int, int)
    scriptfinished = Signal(bool, str)  # success, message
    advance = Signal(int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.flags = InterpreterFlags()

    def parseScript(self, script: str):
        logger.debug(f'Parsing script {script=}')
        parsed = []
        self.namespace = {'_': None}
        for lineno, line in enumerate(script.split('\n'), start=1):
            code = line.strip().split('#')[0].strip()
            if not code:
                # empty line: this is a comment
                logger.debug(f'Line #{lineno} is a comment ({line})')
                parsed.append(Comment(self.instrument, self.namespace, 'None'))
            elif code.startswith('@'):
                # this is a label
                logger.debug(f'Line #{lineno} is a label ({line})')
                parsed.append(Label(self.instrument, self.namespace, code[1:].strip()))
            else:
                # other commands can be handled more easily
                m = re.match(r'^(?P<command>\w+)(\((?P<arguments>.*)\))?$', code)
                if not m:
                    raise ParsingError(lineno, f'Cannot parse line {lineno} of script.')
                else:
                    for subclass in Command.subclasses():
                        assert issubclass(subclass, Command)
                        if subclass.name == m['command']:
                            parsed.append(
                                subclass(self.instrument, self.namespace, m['arguments'] if m['arguments'] else 'None'))
                            break
                    else:
                        raise ParsingError(lineno, f'Unknown command on line {lineno} of script.')
        self.script = parsed

    def execute(self):
        self.flags.reset()
        if self.pointer is not None:
            raise RuntimeError('Script already running')
        logger.debug('Starting script')
        logger.debug('Script:  \n' + '\n'.join([str(cmd) for cmd in self.script]))
        self.pointer = -1
        # clear namespace. Do not create a new dict instance, this is already shared with the commands!
        for key in list(self.namespace):
            del self.namespace[key]
        self.namespace['_'] = None
        self.callstack = []
        self.scriptstarted.emit()
        self.advanceToNextCommand()

    def stop(self):
        if self.pointer is None:
            raise RuntimeError('No script is running')
        self.script[self.pointer].stop()

    @Slot(object)
    def commandFinished(self, returnvalue: Any):
        self.namespace['_'] = returnvalue
        self.advanceToNextCommand()

    @Slot(str)
    def commandFailed(self, message: str):
        self.fail(message)

    @Slot(str, bool)
    def commandJumped(self, label: str, gosub: bool):
        if not label:
            # this is a return command
            try:
                self.pointer = self.callstack.pop()
            except IndexError:
                self.fail('Call stack is empty, nowhere to return.')
            else:
                self.advanceToNextCommand()
            return
        if gosub:
            self.callstack.append(self.pointer)
        linenumbers = [i for i in range(len(self.script)) if
                       isinstance(self.script[i], Label) and self.script[i].argumentstring == label]
        if not linenumbers:
            self.fail(f'Label "{label}" does not exist.')
        elif len(linenumbers) > 1:
            self.fail(f'More than one labels exist with name "{label}".')
        else:
            self.pointer = linenumbers[0]
            self.advanceToNextCommand()

    def _connectCommand(self, command: Command):
        assert isinstance(command, Command)
        command.goto.connect(self.commandJumped)
        command.failed.connect(self.commandFailed)
        command.finished.connect(self.commandFinished)
        command.message.connect(self.commandMessage)
        command.progress.connect(self.commandProgress)

    def _disconnectCommand(self, command: Command):
        assert isinstance(command, Command)
        command.goto.disconnect(self.commandJumped)
        command.failed.disconnect(self.commandFailed)
        command.finished.disconnect(self.commandFinished)
        command.message.disconnect(self.commandMessage)
        command.progress.disconnect(self.commandProgress)

    def advanceToNextCommand(self):
        finishedcommand = self.sender()
        if isinstance(finishedcommand, Command):
            logger.debug(f'Finishedcommand: {finishedcommand.objectName()}')
            self._disconnectCommand(finishedcommand)
        if self.pointer is None:
            logger.warning('Script pointer is None!')
            return
        self.pointer += 1
        if self.pointer >= len(self.script):
            # we reached the end of the script
            logger.debug('Reached the end of the script.')
            self.finish()
        else:
            command = self.script[self.pointer]
            logger.debug(f'Current command is: {command.name=} {command.arguments=}')
            if command.name == 'end':
                self.finish()
                return
            self.advance.emit(self.pointer)
            self._connectCommand(command)
            logger.debug('Executing command.')
            try:
                command.execute()
            except Exception as exc:
                self._disconnectCommand(command)
                self.fail(traceback.format_exc())

    @Slot(str, int, int)
    def commandProgress(self, message: str, current: int, total: int):
        self.progress.emit(message, current, total)

    @Slot(str)
    def commandMessage(self, message: str):
        self.message.emit(message)

    def fail(self, message: str):
        self.pointer = None
        try:
            self.scriptfinished.emit(False, message)
        except Exception as exc:
            logger.error(f'Exception in scriptfinished signal handler: {traceback.format_exc()}')
        if self._panicking == self.PanicState.Panicking:
            super().panichandler()

    def finish(self):
        self.pointer = None
        try:
            self.scriptfinished.emit(True, '')
        except Exception as exc:
            logger.error(f'Exception in the scriptfinished signal handler: {traceback.format_exc()}')
        if self._panicking == self.PanicState.Panicking:
            super().panichandler()

    def panichandler(self):
        self._panicking = self.PanicState.Panicking
        if self.pointer is not None:
            self.stop()
        else:
            super().panichandler()