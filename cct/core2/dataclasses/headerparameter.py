import datetime
import itertools
import logging
from numbers import Real
from typing import List, Tuple, Union, Optional, Any

import dateutil.parser

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HeaderParameter:
    paths: List[Tuple[str, ...]]
    defaultvalue: Optional[Tuple[Any, ...]] = None

    def __init__(self, *paths: Optional[Tuple[str, ...]], default: Optional[Tuple[Any, ...]] = None):
        self.paths = list(paths)
        self.defaultvalue = default

    def __get__(self, instance, objtype):
        lis = []
        for path, default in zip(self.paths,
                                 itertools.repeat(None) if self.defaultvalue is None else self.defaultvalue):
            if path is None:
                lis.append(None)
                continue
            dic = instance._data
            assert isinstance(dic, dict)
            try:
                for pcomponent in path:
                    dic = dic[pcomponent]
                lis.append(dic)
            except KeyError:
                if self.defaultvalue is None:
                    raise
                lis.append(default)
        return tuple(lis)

    def __set__(self, instance, value):
        for path, val in zip(self.paths, value):
            if path is None:
                continue
            dic = instance._data
            assert isinstance(dic, dict)
            for pcomponent in path[:-1]:
                try:
                    dic = dic[pcomponent]
                except KeyError:
                    dic[pcomponent] = {}
                    dic = dic[pcomponent]
            dic[path[-1]] = val

    def __delete__(self, instance):
        pass


class StringHeaderParameter(HeaderParameter):
    def __init__(self, path: Tuple[str, ...], default: Optional[Any] = None):
        super().__init__(path, default=(default,))

    def __get__(self, instance, owner) -> str:
        return str(super().__get__(instance, owner)[0])

    def __set__(self, instance, value: str):
        assert isinstance(value, str)
        super().__set__(instance, [value])


class ValueAndUncertaintyHeaderParameter(HeaderParameter):
    def __init__(self, pathvalue: Optional[Tuple[str, ...]], pathuncertainty: Optional[Tuple[str, ...]],
                 default: Optional[Tuple[Any, Any]] = None):
        super().__init__(pathvalue, pathuncertainty, default=default)

    def __get__(self, instance, owner) -> Tuple[float, Optional[float]]:
        return tuple([float(x) for x in super().__get__(instance, owner)])

    def __set__(self, instance, value: Tuple[float, Optional[float]]):
        if isinstance(value, Real):
            value = float(value)
        elif (isinstance(value, tuple) and isinstance(value[0], Real) and isinstance(value[1], Real) and
              len(value) == 2):
            value = (float(value[0]), float(value[1]))
        else:
            raise TypeError(value)
        super().__set__(instance, value)


class IntHeaderParameter(HeaderParameter):
    def __init__(self, path: Tuple[str, ...], default: Optional[Any] = None):
        super().__init__(path, default=(default,))

    def __get__(self, instance, owner) -> int:
        return int(super().__get__(instance, owner)[0])

    def __set__(self, instance, value: int):
        super().__set__(instance, [int(value)])


class FloatHeaderParameter(HeaderParameter):
    def __init__(self, path: Tuple[str, ...], default: Optional[Any] = None):
        super().__init__(path, default=(default,))

    def __get__(self, instance, owner) -> float:
        return float(super().__get__(instance, owner)[0])

    def __set__(self, instance, value: float):
        super().__set__(instance, [float(value)])


class DateTimeHeaderParameter(HeaderParameter):
    def __init__(self, path: Tuple[str, ...], default: Optional[Any] = None):
        super().__init__(path, default=(default,))

    def __get__(self, instance, owner) -> datetime.datetime:
        val = super().__get__(instance, owner)[0]
        if isinstance(val, datetime.datetime):
            return val
        elif isinstance(val, str):
            return dateutil.parser.parse(val)
        else:
            raise TypeError(val)

    def __set__(self, instance, value: Union[str, datetime.datetime]):
        if isinstance(value, datetime.datetime):
            super().__set__(instance, [value])
        elif isinstance(value, str):
            super().__set__(instance, [dateutil.parser.parse(value)])
        else:
            raise TypeError(value)
