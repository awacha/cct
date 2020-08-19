import logging
import os
import pathlib
import pickle
from typing import Dict, Any, Union, Tuple, KeysView, ValuesView, ItemsView, Optional

from PyQt5 import QtCore

PathLike = Union[os.PathLike, str, pathlib.Path]

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Config(QtCore.QObject):
    """A hierarchical configuration store

    This mimics a Python dictionary, i.e. supporting ['item']-like indexing, but only `str` keys are supported.
    Changes are monitored and if a new value is given, the `changed` signal is emitted.

    Items can be of any type. Dictionaries are handled differently. Whenever a dictionary is assigned to a key, it is
    converted to a `Config` instance.

    """


    changed = QtCore.pyqtSignal(object, object)
    autosave: bool=False
    filename: Optional[str] = None
    _data: Dict[str, Any]
    _autosaveinhibited: bool = False
    _modificationcount: int = 0

    def __init__(self, dicorfile: Union[None, Dict[str, Any], str] = None, autosave: bool=False):
        super().__init__()
        self._data = {}
        if dicorfile is None:
            pass
        elif isinstance(dicorfile, dict):
            self.__setstate__({} if dicorfile is None else dicorfile.copy())
        elif isinstance(dicorfile, str):
            self.load(dicorfile, update=False)
        self.autosave = autosave
        self.changed.connect(self.onChanged)

    def onChanged(self, path: Tuple[str, ...], value: Any):
        if self.autosave and (self.filename is not None) and (not self._autosaveinhibited):
            self.save(self.filename)

    def __setitem__(self, key: Union[str, Tuple[str]], value: Any):
        if isinstance(key, tuple) and len(key) > 1:
            subconfig = self._data[key[0]]
            assert isinstance(subconfig, Config)
            return subconfig.__setitem__(key[1:], value)
        elif isinstance(key, tuple) and len(key) == 1:
            key = key[0]
        elif isinstance(key, tuple) and len(key) == 0:
            raise ValueError('Empty tuples cannot be Config keys!')
        if not isinstance(value, dict):
            if key not in self._data:
                self._data[key] = value
                self.changed.emit((key,), value)
            else:
                # key already present, see if they are different
                if self._data[key] != value:
                    self._data[key] = value
                    # value changed, emit the signal
                    self.changed.emit((key, ), value)
                else:
                    pass
        else:
            # convert it to a Config instance
            cnf = Config(value)
            if (key not in self._data) or (not isinstance(self._data[key], Config)):
                self._data[key] = cnf
                self._data[key].changed.connect(self._subConfigChanged)
                self.changed.emit((key,), cnf)
            elif cnf is not self._data[key]:
                self._data[key].update(cnf)
            else:
                # setting the same config: do nothing.
                pass
        self._modificationcount += 1

    def __delitem__(self, key: Union[str, Tuple[str, ...]]):
        logger.debug(f'Deleting key {key}')
        if isinstance(key, str):
            key = (key,)
        logger.debug(f'Key normalized to {key}')
        dic = self
        for k in key[:-1]:
            dic = dic[k]
        assert isinstance(dic, Config)
        if isinstance(dic._data[key[-1]], Config):
            dic._data[key[-1]].changed.disconnect(self._subConfigChanged)
        del dic._data[key[-1]]
        self._modificationcount += 1

    def __getitem__(self, item: Union[str, Tuple[str, ...]]):
        if isinstance(item, str):
            return self._data[item]
        elif isinstance(item, int):
            return self._data[item]
        else:
            dic = self
            for key in item:
                dic = dic[key]
            return dic

    def __getstate__(self) -> Dict[str, Any]:
        dic = {}
        for k in self:
#            logger.debug(f'In __getstate__: {k}. Keys in self: {list(self.keys())}')
            if isinstance(self[k], Config):
                dic[k] = self[k].__getstate__()
            else:
                dic[k] = self[k]
        return dic

    def keys(self) -> KeysView:
        return self._data.keys()

    def values(self) -> ValuesView:
        return self._data.values()

    def items(self) -> ItemsView:
        return self._data.items()

    def _subConfigChanged(self, path, newvalue):
        cnf = self.sender()
        # find the key for this `Config` instance
        try:
            key = [k for k in self.keys() if self[k] is cnf][0]
        except IndexError:
            # this `Config` instance does not belong to us, disconnect the signal.
            cnf.changed.disconnect(self._subConfigChanged)
        else:
            # extend the path with the key and re-emit the signal.
            self.changed.emit((key,) + path, newvalue)
            self._modificationcount += 1

    def update(self, other: Union["Config", Dict]):
        for key in other:
            logger.debug(f'Updating {key=}')
            if isinstance(other[key], Config) or isinstance(other[key], dict):
                if (key in self) and isinstance(self[key], Config):
                    logger.debug(f'Key {key} is a Config')
                    self[key].update(other[key])
                else:
                    logger.debug(f'scalar -> dict of key {key}')
                    self[key] = other[key]
            else:
                logger.debug(f'simple update of key {key}')
                self[key] = other[key]

    def __iter__(self):
        return self._data.__iter__()

    def __contains__(self, item: Union[str, Tuple[str, ...]]):
        if isinstance(item, str):
            return item in self._data
        else:
            dic = self
            for key in item[:-1]:
                dic = dic[key]
            return item[-1] in dic

    def load(self, picklefile: PathLike, update: bool=True):
        if not update:
            logger.debug(f'Loading configuration from {picklefile}')
            with open(picklefile, 'rb') as f:
                data = pickle.load(f)
            logger.debug('Loaded a pickle file')
            self.__setstate__(data)
        else:
            logger.debug(f'Loading configuration with update')
            other = Config(picklefile)
            self.update(other)
        logger.info(f'Loaded configuration from {picklefile}')
        self.filename = picklefile

    def save(self, picklefile: PathLike):
        #logger.debug(f'Saving configuration to {picklefile}')
        with open(picklefile, 'wb') as f:
            pickle.dump(self.__getstate__(), f)
        logger.info(f'Saved configuration to {picklefile}')

    def __setstate__(self, dic: Dict[str, Any]):
        self._data = dic
        for key in self._data:
            # convert dictionaries to `Config` instances and connect to their changed signals.
            if isinstance(self._data[key], dict):
                self._data[key] = Config(self._data[key])
                self._data[key].changed.connect(self._subConfigChanged)

    asdict = __getstate__

    def __str__(self):
        return str(self.__getstate__())

    def __repr__(self):
        return repr(self.__getstate__())

    def inhibitAutoSave(self):
        self._autosaveinhibited = True
        self._modificationcount = 0

    def enableAutoSave(self):
        if self._autosaveinhibited and self._modificationcount and (self.filename is not None):
            self.save(self.filename)
        self._autosaveinhibited = False
        self._modificationcount = 0

    def __len__(self):
        return len(self._data)

    def setdefault(self, key: str, value: Any) -> Any:
        try:
            return self._data[key]
        except KeyError:
            self[key]=value
            return self[key]
