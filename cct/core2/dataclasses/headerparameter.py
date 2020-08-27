from typing import List, Tuple


class HeaderParameter:
    paths = List[Tuple[str, ...]]

    def __init__(self, *paths: Tuple[str, ...]):
        self.paths = list(paths)

    def __get__(self, instance, objtype):
        lis = []
        for path in self.paths:
            dic = instance._data
            assert isinstance(dic, dict)
            for pcomponent in path:
                dic = dic[pcomponent]
            lis.append(dic)
        return lis

    def __set__(self, instance, value):
        for path, val in zip(self.paths, value):
            logger.debug(f'Setting {path=} to {val=}')
            dic = instance._data
            assert isinstance(dic, dict)
            for pcomponent in path[:-1]:
                dic = dic[pcomponent]
            dic[path[-1]] = val

    def __delete__(self, instance):
        pass


class StringHeaderParameter(HeaderParameter):
    def __init__(self, path: Tuple[str, ...]):
        super().__init__(path)

    def __get__(self, instance, owner) -> str:
        return str(super().__get__(instance, owner)[0])

    def __set__(self, instance, value: str):
        assert isinstance(value, str)
        super().__set__(instance, [value])


class ValueAndUncertaintyHeaderParameter(HeaderParameter):
    def __init__(self, pathvalue: Tuple[str, ...], pathuncertainty: Tuple[str, ...]):
        super().__init__(pathvalue, pathuncertainty)

    def __get__(self, instance, owner) -> Tuple[float, float]:
        return tuple([float(x) for x in super().__get__(instance, owner)])

    def __set__(self, instance, value: Tuple[float, float]):
        super().__set__(instance, value)


class IntHeaderParameter(HeaderParameter):
    def __init__(self, path: Tuple[str, ...]):
        super().__init__(path)

    def __get__(self, instance, owner) -> int:
        return int(super().__get__(instance, owner)[0])

    def __set__(self, instance, value: int):
        assert isinstance(value, int)
        super().__set__(instance, [value])
