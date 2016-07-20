from .command import Command, CommandArgumentError


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
    name = 'goto'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly one positional argument.'.format(self.name))
        self.label = str(self.args[0])

    def execute(self):
        raise GotoException(self.label)


class Gosub(Command):
    """Unconditional returnable jump to a label.

    Invocation: gosub(<labelname>)

    Arguments:
        <labelname>: a string containing the name of the destination label

    Remarks:
        Can only be used in scripts.
    """
    name = 'gosub'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly one positional argument.'.format(self.name))
        self.label = str(self.args[0])

    def execute(self):
        raise GosubException(self.label)


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
    name = 'goif'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 2:
            raise CommandArgumentError('Command {} requires exactly two positional arguments.'.format(self.name))
        self.label = str(self.args[0])
        self.condition = bool(self.args[1])

    def execute(self):
        if self.condition:
            raise GotoException(self.label)
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
    name = 'gosubif'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 2:
            raise CommandArgumentError('Command {} requires exactly two positional arguments.'.format(self.name))
        self.label = str(self.args[0])
        self.condition = bool(self.args[1])

    def execute(self):
        if self.condition:
            raise GosubException(self.label)
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
    name = 'return'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if self.args:
            raise CommandArgumentError('Command {} does not support positional arguments.'.format(self.name))

    def execute(self):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 2:
            raise CommandArgumentError('Command {} requires exactly two positional arguments.'.format(self.name))
        self.label = str(self.args[0])
        self.flag = str(self.args[1])

    def execute(self):
        if self.interpreter.is_flag(self.flag):
            raise GotoException(self.label)
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 2:
            raise CommandArgumentError('Command {} requires exactly two positional arguments.'.format(self.name))
        self.label = str(self.args[0])
        self.flag = str(self.args[1])

    def execute(self):
        if self.interpreter.is_flag(self.flag):
            raise GosubException(self.label)
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly one positional argument.'.format(self.name))
        self.flag = str(self.args[0])

    def execute(self):
        self.interpreter.clear_flag(self.flag)
        self.emit('message', 'Clearing flag: {}'.format(self.flag))
        self.idle_return(None)


class SetFlag(Command):
    """Set a flag to ON state.

    Invocation: setflag(<flagname>)

    Arguments:
        <flagname>: a string containing the name of the flag

    Remarks:
        Can only be used in scripts.
    """
    name = 'setflag'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.kwargs:
            raise CommandArgumentError('Command {} does not support keyword arguments.'.format(self.name))
        if len(self.args) != 1:
            raise CommandArgumentError('Command {} requires exactly one positional argument.'.format(self.name))
        self.flag = str(self.args[0])

    def execute(self):
        self.interpreter.set_flag(self.flag)
        self.emit('message', 'Setting flag: {}'.format(self.flag))
        self.idle_return(None)
