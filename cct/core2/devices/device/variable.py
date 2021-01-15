import time
from math import inf
from typing import Any, Optional


class Variable:
    """Represents a state variable of a device"""
    name: str  # the name of the variable
    value: Any = None  # the actual value of the variable
    previousvalue: Any = None  # the previous value of the variable
    timestamp: Optional[float] = None  # time the actual value was read
    lastquery: Optional[float] = None  # time when the last query has been sent or None if there are no unreplied queries
    lastchange: Optional[float] = None  # time when the value was last changed
    querytimeout: float  # current querying period. If None, this variable will never be queried
    defaulttimeout: float  # default querying period
    queryretries: int = 0

    def __init__(self, name: str, querytimeout: Optional[float]):
        self.name = name
        self.querytimeout = querytimeout
        self.defaulttimeout = querytimeout

    def update(self, newvalue: Any) -> bool:
        self.lastquery = None
        self.timestamp = time.monotonic()
        if (self.lastchange is not None) and ((newvalue == self.value) or (newvalue is self.value)):
            return False
        self.previousvalue = self.value
        self.value = newvalue
        self.lastchange = self.timestamp
        return True

    def setTimeout(self, timeout: Optional[float] = None):
        self.querytimeout = self.defaulttimeout if timeout is None else timeout

    def age(self) -> float:
        if self.timestamp is None:
            return inf
        else:
            return time.monotonic() - self.timestamp

    def hasValidValue(self) -> bool:
        return self.timestamp is not None

    def queriable(self) -> bool:
        return self.querytimeout is not None

    def overdue(self, timestamp: Optional[float] = None) -> float:
        if self.timestamp is None:
            # variables which are never queried are long overdue
            return inf
        elif self.querytimeout is None:
            # variables which are not queriable are not overdue
            return -inf
        else:
            if timestamp is None:
                timestamp = time.monotonic()
            return (timestamp - self.timestamp) - self.querytimeout

    def __str__(self) -> str:
        return (f'Variable {self.name}:\n'
                f'   value: {self.value}\n'
                f'   previous value: {self.previousvalue}\n'
                f'   last refreshed: {self.timestamp}\n'
                f'   last changed: {self.lastchange}\n'
                f'   last queried: {self.lastquery}\n'
                f'   time now: {time.monotonic()}\n'
                f'   query timeout: {self.querytimeout}\n'
                f'   default query timeout: {self.defaulttimeout}\n'
                f'   overdue: {self.overdue()} seconds\n'
                f'   has valid value: {self.hasValidValue()}\n'
                f'   queriable: {self.queriable()}')