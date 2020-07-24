import datetime
import enum
from numbers import Real
from typing import Any, Type

import dateutil.parser


class LockState(enum.Enum):
    LOCKED = 'locked'
    UNLOCKED = 'unlocked'


class LockableAttribute:
    name: str
    defaultvalue: Any
    defaultlocked: bool

    def __init__(self, name: str, value: Any, locked: bool = False):
        self.name = name
        self.defaultvalue = value
        self.defaultlocked = locked

    def __get__(self, instance: object, type_=None) -> Any:
        return instance.__dict__.setdefault(f'_lockable_{self.name}.value', self._normalize(self.defaultvalue))

    def __set__(self, instance: object, value: Any):
        if isinstance(value, LockState):
            if value == LockState.LOCKED:
                instance.__dict__[f'_lockable_{self.name}.locked'] = True
            elif value == LockState.UNLOCKED:
                instance.__dict__[f'_lockable_{self.name}.locked'] = False
            else:
                raise ValueError(value)
        elif instance.__dict__.setdefault(f'_lockable_{self.name}.locked', self.defaultlocked):
            raise ValueError(f'Cannot set {self.name}: locked!')
        else:
            instance.__dict__[f'_lockable_{self.name}.value'] = self._normalize(value)

    def __delete__(self, instance):
        try:
            del instance.__dict__[f'_lockable_{self.name}.locked']
        except KeyError:
            pass
        try:
            del instance.__dict__[f'_lockable_{self.name}.value']
        except KeyError:
            pass

    def _normalize(self, value: Any):
        raise NotImplementedError


class LockableFloat(LockableAttribute):
    def _normalize(self, value: Any):
        if isinstance(value, Real):
            return float(value), 0.0
        elif (isinstance(value, tuple)
              and (len(value) == 2)
              and isinstance(value[0], Real)
              and isinstance(value[1], Real)):
            return float(value[0]), float(value[1])
        else:
            raise TypeError(value)


class LockableString(LockableAttribute):
    def _normalize(self, value: Any):
        if isinstance(value, str):
            return value
        else:
            raise TypeError(value)


class LockableOptionalString(LockableAttribute):
    def _normalize(self, value: Any):
        if value is None:
            return None
        elif value == '__none__':
            return None
        elif isinstance(value, str):
            return value
        else:
            raise TypeError(value)


class LockableDate(LockableAttribute):
    def _normalize(self, value: Any):
        if value is None:
            return datetime.date.today()
        elif isinstance(value, datetime.date):
            return value
        elif isinstance(value, datetime.datetime):
            return value.date()
        elif isinstance(value, str):
            if value.lower() == '__none__':
                return datetime.date.today()
            else:
                return dateutil.parser.parse(value).date()
        else:
            raise TypeError(value)


class LockableEnum(LockableAttribute):
    enumclass: Type[enum.Enum]

    def __init__(self, name: str, enumclass: Type[enum.Enum], value: Any, locked: bool = False):
        self.enumclass = enumclass
        super().__init__(name, value, locked)

    def _normalize(self, value: Any):
        return self.enumclass(value)

