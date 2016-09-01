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


class ScriptEndException(JumpException):
    pass
