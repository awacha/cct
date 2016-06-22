from gi.repository import GLib

from .command import Command


class JumpException(Exception):
    pass

class GotoException(JumpException):
    pass

class GosubException(JumpException):
    pass

class ReturnException(JumpException):
    pass

class PassException(JumpException):
    pass

class Goto(Command):
    """Unconditional one-way jump to a label.

    Invocation: goto(<labelname>)

    Arguments:
        <labelname>: a string containing the name of the destination label

    Remarks:
        Can only be used in scripts.
    """
    name='goto'

    def execute(self, interpreter, arglist, instrument, namespace):
        raise GotoException(arglist[0])


class Gosub(Command):
    """Unconditional returnable jump to a label.

    Invocation: gosub(<labelname>)

    Arguments:
        <labelname>: a string containing the name of the destination label

    Remarks:
        Can only be used in scripts.
    """
    name='gosub'

    def execute(self, interpreter, arglist, instrument, namespace):
        raise GosubException(arglist[0])

class GoIf(Command):
    """Conditional one-way jump to a label

    Invocation: goif(<labelname>, <expression>)

    Arguments:
        <labelname>: a string containing the name of the destination label
        <expression>: a valid expression. If this evaluates to true, the jump
            is done. Otherwise this command is a no-op.

    Remarks:
        Can only be used in scripts.
    """
    name='goif'

    def execute(self, interpreter, arglist, instrument, namespace):
        if arglist[1]:
            raise GotoException(arglist[0])
        else:
            raise PassException()

class GosubIf(Command):
    """Conditional returnable jump to a label

    Invocation: gosubif(<labelname>, <expression>)

    Arguments:
        <labelname>: a string containing the name of the destination label
        <expression>: a valid expression. If this evaluates to true, the jump
            is done. Otherwise this command is a no-op.

    Remarks:
        Can only be used in scripts.
    """
    name='gosubif'

    def execute(self, interpreter, arglist, instrument, namespace):
        if arglist[1]:
            raise GosubException(arglist[0])
        else:
            raise PassException()

class Return(Command):
    """Return to the previous gosub command

    Invocation: return()

    Arguments:
        None

    Remarks:
        Can only be used in scripts.
    """
    name='return'

    def execute(self, interpreter, arglist, instrument, namespace):
        raise ReturnException()


class GoOnFlag(Command):
    """Conditional one-way jump to a label if a flag is set

    Invocation: goonflag(<labelname>, <flagname>)

    Arguments:
        <labelname>: a string containing the name of the destination label
        <flagname>: a string containing the name of the flag

    Remarks:
        Can only be used in scripts.
    """
    name = 'goonflag'

    def execute(self, interpreter, arglist, instrument, namespace):
        if interpreter.is_flag(str(arglist[1])):
            raise GotoException(arglist[0])
        else:
            raise PassException()


class GosubOnFlag(Command):
    """Conditional returnable jump to a label if a flag is set

    Invocation: gosubonflag(<labelname>, <flagname>)

    Arguments:
        <labelname>: a string containing the name of the destination label
        <flagname>: a string containing the name of the flag

    Remarks:
        Can only be used in scripts.
    """
    name = 'gosubonflag'

    def execute(self, interpreter, arglist, instrument, namespace):
        if interpreter.is_flag(str(arglist[1])):
            raise GosubException(arglist[0])
        else:
            raise PassException()

class ClearFlag(Command):
    """Set a flag to OFF state.

    Invocation: clearflag(<flagname>)

    Arguments:
        <flagname>: a string containing the name of the flag

    Remarks:
        Can only be used in scripts.
    """
    name = 'clearflag'

    def execute(self, interpreter, arglist, instrument, namespace):
        self._flag=str(arglist[0])
        self._interpreter=interpreter
        GLib.idle_add(self._return)

    def _return(self):
        self._interpreter.clear_flag(self._flag)
        self.emit('message', 'Clearing flag: {}'.format(self._flag))
        self.emit('return', None)
        return False

class SetFlag(Command):
    """Set a flag to ON state.

    Invocation: setflag(<flagname>)

    Arguments:
        <flagname>: a string containing the name of the flag

    Remarks:
        Can only be used in scripts.
    """
    name = 'setflag'

    def execute(self, interpreter, arglist, instrument, namespace):
        self._flag=str(arglist[0])
        self._interpreter=interpreter
        GLib.idle_add(self._return)

    def _return(self):
        self._interpreter.set_flag(self._flag)
        self.emit('message', 'Setting flag: {}'.format(self._flag))
        self.emit('return', None)
        return False
