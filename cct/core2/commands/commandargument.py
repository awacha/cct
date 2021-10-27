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

    def __str__(self):
        return f'{self.name}: {self.description}' + (
            f' (default: {self.defaultvalue}' if self.defaultvalue is not None else '')


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
    casesensitive: bool

    def __init__(self, name: str, description: str, choices: Sequence[str], defaultvalue: Optional[Any] = None,
                 casesensitive: bool = False):
        super().__init__(name, description, defaultvalue)
        if not casesensitive:
            choices = [c.lower() for c in choices]
        self.casesensitive = casesensitive
        self.choices = list(choices)

    def validate(self, argument: Any) -> str:
        if (str(argument) if self.casesensitive else str(argument).lower()) in self.choices:
            return str(argument)
        else:
            raise ValueError(f'Invalid value: {argument}: not among the permissible choices')


class AnyArgument(CommandArgument):
    def validate(self, argument: Any) -> Any:
        return argument
