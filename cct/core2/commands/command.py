from typing import Optional, Dict, Any, List, Type, final, Tuple
import logging

from PyQt5 import QtCore

from .commandargument import CommandArgument

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
    arguments: List[CommandArgument]
    argumentstring: str
    description: str
    failed = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal(str, int, int)  # message, current, total
    message = QtCore.pyqtSignal(str)
    goto = QtCore.pyqtSignal(str, bool)
    parsed_arguments: Tuple[Any]
    _finished: bool = False

    class CommandException(Exception):
        pass

    def __init__(self, instrument, namespace: Dict[str, Any], arguments: str):
        super().__init__()
        self.namespace = namespace
        self.instrument = instrument
        self.argumentstring = arguments

    @final
    def execute(self):
#        logger.debug(f'Executing command {self.name}')
        self._finished = False
        if self._timer is not None:
            raise self.CommandException('Already running.')
        self.initialize(*self.parseArguments())
        if self._finished: # the job is already done in the initialize() method, no need to set up a timer
            return
        if self.timerinterval is not None:
            self._timer = self.startTimer(int(self.timerinterval * 1000))

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        # self.finish(self.namespace['_'])
        pass

    def initialize(self, *args: Any):
        pass

    def finalize(self):
        pass

    @final
    def jump(self, label: str, gosub: bool = False):
        logger.debug(f'Jumping to label {label} from command {self.name}. {gosub=}')
        if self._timer is not None:
            self.killTimer(self._timer)
            self._timer = None
        try:
            self.finalize()
        finally:
            self._finished = True
            self.goto.emit(label, gosub)

    @final
    def fail(self, message: str):
        logger.debug(f'Failing command {self.name}')
        if self._timer is not None:
            self.killTimer(self._timer)
            self._timer = None
        try:
            self.finalize()
        finally:
            self._finished = True
            self.failed.emit(str(message))

    @final
    def finish(self, returnvalue: Any):
        logger.debug(f'Finishing command {self.name}')
        if self._timer is not None:
            self.killTimer(self._timer)
            self._timer = None
        try:
            self.finalize()
        finally:
            self._finished = True
            self.finished.emit(str(returnvalue))

    def parseArguments(self) -> Any:
        logger.debug(f'Parsing arguments: {self.argumentstring=}')
        args = eval(self.argumentstring, None, self.namespace)
        if args is None:
            args = ()
        elif not isinstance(args, tuple):
            # happens in the case of a single argument
            args = (args,)
        if len(args) < len(self.arguments):
            # adding default values
            args = args + tuple([a.defaultvalue for a in self.arguments[len(args):]])
        self.parsed_arguments = args
        return args

    def stop(self):
        self.fail('Stopping command on user request')

    @classmethod
    @final
    def subclasses(cls) -> List[Type["Command"]]:
        lis = []
        for c in cls.__subclasses__():
            lis.append(c)
            lis.extend(c.subclasses())
        return lis

    @classmethod
    def helptext(cls) -> str:
        s = cls.description+'\n\n'
        s += f'Invocation:\n    {cls.name}'
        if ... in cls.arguments[:-1]:
            raise TypeError('Argument specification "..." can only be the last one in a command\'s argument list.')
        if cls.arguments:
            s += '(' + ', '.join(['...' if a is ... else a.name for a in cls.arguments]) + ')\n\nArguments:\n'
            s += '\n'.join([f'    {a}' for a in cls.arguments if a is not ...])
        s += '\n'
        return s

    def __str__(self) -> str:
        return f'{self.name}({self.argumentstring})'


class InstantCommand(Command):
    parsed_arguments: Any
    timerinterval = 0

    @final
    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        try:
            result = self.run(*self.parsed_arguments)
            self.finish(result)
        except Exception as exc:
            self.fail(str(exc))

    def run(self, *args: Any) -> Any:
        raise NotImplementedError

    @final
    def stop(self):
        pass


class JumpCommand(Command):
    parsed_arguments: Any
    timerinterval = 0

    @final
    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        try:
            label, isgosub = self.run(*self.parsed_arguments)
            if label is not None:
                self.jump(label, isgosub)
            else:
                self.finish(self.namespace['_'])
        except Exception as exc:
            self.fail(str(exc))

    def run(self, *args: Any) -> Tuple[str, bool]:
        raise NotImplementedError