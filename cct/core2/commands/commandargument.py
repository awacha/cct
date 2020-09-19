from typing import Optional, Any, Sequence, List


class CommandArgument:
    name: str
    description: str
    defaultvalue: Any

    def __init__(self, name: str, description: str, defaultvalue: Optional[Any] = None):
        self.name = name
        self.description = description
        self.defaultvalue = defaultvalue

    def validate(self, argument: Any):
        raise NotImplementedError


class StringArgument(CommandArgument):
    def validate(self, string: Any) -> str:
        return str(string)


class IntArgument(CommandArgument):
    def validate(self, argument: Any) -> int:
        return int(argument)


class FloatArgument(CommandArgument):
    def validate(self, argument: Any) -> float:
        return float(argument)


class StringChoicesArgument(CommandArgument):
    choices: List[str]

    def __init__(self, name: str, description: str, choices: Sequence[str], defaultvalue: Optional[Any] = None):
        super().__init__(name, description, defaultvalue)
        self.choices = list(choices)

    def validate(self, argument: Any) -> str:
        if str(argument) in self.choices:
            return str(argument)
        else:
            raise ValueError(f'Invalid value: {argument}: not among the permissible choices')


class AnyArgument(CommandArgument):
    def validate(self, argument: Any) -> Any:
        return argument