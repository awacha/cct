import re
from typing import Any, Dict, List, Optional

from PyQt5 import QtCore

from .component import Component
from ...commands import Command, Comment, Label


class Interpreter(QtCore.QObject, Component):
    script: List[Command] = None
    namespace: Dict[str, Any] = None
    pointer: Optional[int] = None  # points to the current command
    callstack: List[int] = None

    started = QtCore.pyqtSignal()
    message = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(str, int, int)
    failed = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()
    advance = QtCore.pyqtSignal(int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def parseScript(self, script: str):
        parsed = []
        self.namespace={'_':None}
        for lineno, line in enumerate(script.split('\n'), start=1):
            code = line.strip().split('#')[0].strip()
            if not code:
                # empty line: this is a comment
                parsed.append(Comment(self.instrument, self.namespace, 'None'))
            elif code.startswith('@'):
                # this is a label
                parsed.append(Label(self.instrument, self.namespace, code[1:].strip()))
            else:
                # other commands can be handled more easily
                m = re.match(r'^(?P<command>\w+)(\((?P<arguments>.*)\))?$', code)
                if not m:
                    raise ValueError(f'Cannot parse line {lineno} of script.')
                else:
                    for subclass in Command.__subclasses__():
                        assert issubclass(subclass, Command)
                        if subclass.name == m['command']:
                            parsed.append(subclass(self.instrument, self.namespace, m['arguments'] if m['arguments'] else 'None'))
        self.script = parsed

    def execute(self):
        if self.pointer is not None:
            raise RuntimeError('Script already running')
        self.pointer = 0
        # clear namespace. Do not create a new dict instance, this is already shared with the commands!
        for key in self.namespace:
            del self.namespace[key]
        self.namespace['_'] = None
        self.callstack = []
        self.started.emit()
        self.advanceToNextCommand()

    def commandFinished(self, returnvalue: Any):
        self.namespace['_'] = returnvalue
        self.nextCommand()

    def commandFailed(self, message: str):
        self.fail(message)

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
            self.callstack.insert(0, self.pointer)
        linenumbers = [i for i in range(len(self.script)) if isinstance(self.script[i], Label) and eval(self.script[i].arguments) == label]
        if not linenumbers:
            self.fail(f'Label "{label}" does not exist.')
        elif len(linenumbers) > 1:
            self.fail(f'More than one labels exist with name "{label}".')
        else:
            self.pointer = linenumbers[0]
            self.advanceToNextCommand()

    def advanceToNextCommand(self):
        finishedcommand = self.sender()
        if finishedcommand is not None:
            assert isinstance(finishedcommand, Command)
            finishedcommand.goto.disconnect(self.commandJumped)
            finishedcommand.failed.disconnect(self.commandFailed)
            finishedcommand.finished.disconnect(self.commandFinished)
        self.pointer += 1
        if self.pointer >= len(self.script):
            # we reached the end of the script
            self.finish()
        else:
            command = self.script[self.pointer]
            if command.name == 'end':
                self.finish()
                return
            self.advance.emit(self.pointer)
            command.goto.connect(self.commandJumped)
            command.failed.connect(self.commandFailed)
            command.finished.connect(self.commandFinished)
            command.execute()

    def commandProgress(self, message: str, current: int, total: int):
        self.progress.emit(message, current, total)

    def commandMessage(self, message: str):
        self.message.emit(message)

    def fail(self, message: str):
        self.failed.emit(message)

    def finish(self):
        self.finished.emit()
