from typing import Optional, Dict, Any

from PyQt5 import QtCore


class Command(QtCore.QObject):
    """Commands are building blocks of CCTs scripting mechanism. Each line of a script corresponds to exactly one
    command and vice verse. Commands can have positional arguments which are Python expressions and eval()-ed before
    each run. Commands can be re-used e.g. in loops.

    The life cycle of a command is:
    1) instantiation when the script is parsed
    2) when a command is executed, the `execute()` method is called.
    3) while the command is running, it can emit the following signals:
        - progress(message: string, current index: int, total count: int):
            information for displaying the progress of the command. If indefinite, current index and total count must
            both be set to 0.
        - message(message: string):
            a message should be displayed to the user in the status bar or in the log
    4) exactly one of the following signals is issued at the end of the execution of the command:
        - finished(return value):
            signifies a successful finish. This signal should not emitted directly, subclasses must call the finish()
            method
        - goto(label name, gosub):
            requests a jump to the named label. If `gosub` is True, the line number of this command is stored so a
            subsequent `return` command may instruct the interpreter to jump back here. Subclasses should not emit this
            signal directly but call the jump() method.
        - failed(error message):
            signifies failure of the command. This should result in the termination of the script. Subclasses should not
            emit this signal directly but call the fail() method.
        Note that these signals must not be emitted from the execute() method. The interpreter depends on this. If the
        command is instantaneous, set the timerinterval attribute to zero and call finish() in the timerEvent() method.
    5) in subclasses you should not overload the execute() method. Instead use the initialize() method to do
        initialization tasks before execution. During execution, the timerEvent() method can be used to check if the
        command ended and emit signals, including multi-emit and final ones.

    The arguments are received by the constructor as a single string and stored in the `arguments` attribute. At each
    execution the `execute` method calls the `parseArguments` method to make meaningful values, taking the variables in
    the local environment into account (see below). Before calling `eval()` on the argument string, it adds a set of
    parentheses around it. Thus for single arguments as in `sleep(10)` -> initialize(10) will be called. For more
    arguments, e.g. `moveto('SampleY', 70)` -> initialize(('SampleY', 70)) will be called, i.e. the arguments are given
    in a tuple.

    The local environment is also passed as an argument to __init__. This is a dictionary of variable names and values.
    The same instance of this dictionary is shared with all other commands and the interpreter itself. There is one
    special variable '_', which is the result of the previous command or None.

    """

    name: str = None
    instrument = None
    timerinterval: float = 0.1
    _timer: Optional[int] = None
    namespace: Dict[str, Any] = None
    arguments: Any = None
    failed = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal(str, int, int)
    message = QtCore.pyqtSignal(str)
    goto = QtCore.pyqtSignal(str, bool)

    class CommandException(Exception):
        pass

    def __init__(self, instrument, namespace: Dict[str, Any], arguments: str):
        super().__init__()
        self.namespace = namespace
        self.arguments = list(arguments)
        self.instrument = instrument

    def execute(self):
        if self._timer is not None:
            raise self.CommandException('Already running.')
        self.initialize(self.parseArguments())
        if self.timerinterval is not None:
            self._timer = self.startTimer(int(self.timerinterval * 1000))

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        self.finish(self.namespace['_'])

    def initialize(self, arguments: Any):
        pass

    def jump(self, label: str, gosub: bool = False):
        if self._timer is not None:
            self.killTimer(self._timer)
            self._timer = None
        self.goto.emit(label, gosub)

    def fail(self, message: str):
        if self._timer is not None:
            self.killTimer(self._timer)
            self._timer = None
        self.failed.emit(message)

    def finish(self, returnvalue: Any):
        if self._timer is not None:
            self.killTimer(self._timer)
            self._timer = None
        self.finished.emit(returnvalue)

    def parseArguments(self) -> Any:
        return eval(self.arguments)

    def stop(self):
        self.fail('Stopping command on user request')