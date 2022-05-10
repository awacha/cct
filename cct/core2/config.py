import logging
import os
import pathlib
import pickle
from typing import Dict, Any, Union, Tuple, KeysView, ValuesView, ItemsView, Optional

from PyQt5 import QtCore

PathLike = Union[os.PathLike, str, pathlib.Path]

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Config(QtCore.QObject):
    """A hierarchical configuration store

    This mimics a Python dictionary, i.e. supporting ['item']-like indexing, but only `str` keys are supported.
    Changes are monitored and if a new value is given, the `changed` signal is emitted.

    Items can be of any type. Dictionaries are handled differently. Whenever a dictionary is assigned to a key, it is
    converted to a `Config` instance.

    """

    changed = QtCore.pyqtSignal(object, object)
    filename: Optional[str] = None
    _data: Dict[str, Any]
    _modificationcount: int = 0
    _autosavetimeout: float = 0.1
    _autosavetimer: Optional[int] = None

    def __init__(self, dicorfile: Union[None, Dict[str, Any], str] = None):
        super().__init__()
        self._data = {}
        if dicorfile is None:
            pass
        elif isinstance(dicorfile, dict):
            self.__setstate__({} if dicorfile is None else dicorfile.copy())
        elif isinstance(dicorfile, str):
            self.load(dicorfile, update=False)
        self.changed.connect(self.onChanged)

    def autosave(self):
        if self.filename is not None:
            if self._autosavetimer is not None:
                self.killTimer(self._autosavetimer)
                self._autosavetimer = None
            self._autosavetimer = self.startTimer(int(self._autosavetimeout*1000), QtCore.Qt.PreciseTimer)

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        if timerEvent.timerId() == self._autosavetimer:
            # do autosave
            self.killTimer(timerEvent.timerId())
            self._autosavetimer = None
            self.save(self.filename)

    def onChanged(self, path: Tuple[str, ...], value: Any):
        self.autosave()

    def __setitem__(self, key: Union[int, str, Tuple[Union[str, int]]], value: Any):
        logger.debug(f'Config.__setitem__({key}, {value})')
        if isinstance(key, tuple) and len(key) > 1:
            subconfig = self._data[key[0]]
            assert isinstance(subconfig, Config)
            return subconfig.__setitem__(key[1:], value)
        elif isinstance(key, tuple) and len(key) == 1:
            key = key[0]
        elif isinstance(key, tuple) and len(key) == 0:
            raise ValueError('Empty tuples cannot be Config keys!')
        elif not isinstance(key, (str, int)):
            logger.error(f'Funny key type: {key}, {type(key)}')
            assert False
        if not isinstance(value, dict):
            if key not in self._data:
                self._data[key] = value
                self.changed.emit((key,), value)
            else:
                # key already present, see if they are different
                if not (isinstance(self._data[key], type(value)) and (self._data[key] == value)):
                    self._data[key] = value
                    # value changed, emit the signal
                    logger.debug(f'Key value changed, emitting change signal.')
                    self.changed.emit((key, ), value)
                else:
                    logger.debug(f'No need to change key {key}: type and value are the same')
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
        self.autosave()

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
            try:
                dic._data[key[-1]].changed.disconnect(self._subConfigChanged)
            except TypeError:
                pass
        del dic._data[key[-1]]
        self.autosave()

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
            logger.warning(f'Disconnecting stale `changed` signal handler. Keys in stale config: {list(cnf.keys())}')
            cnf.changed.disconnect(self._subConfigChanged)
        else:
            # extend the path with the key and re-emit the signal.
            logger.debug(f'Config change in subconfig "{key}", path {path}. Emitting `changed` signal with path "{key}"')
            self.changed.emit((key,) + path, newvalue)
        self.autosave()

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
        self.autosave()

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
        self.filename = picklefile
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

    def save(self, picklefile: Optional[PathLike] = None):
        if picklefile is None:
            picklefile = self.filename
        #logger.debug(f'Saving configuration to {picklefile}')
        dirs, filename = os.path.split(picklefile)
        os.makedirs(dirs, exist_ok=True)
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

    def __len__(self):
        return len(self._data)

    def setdefault(self, key: str, value: Any) -> Any:
        try:
            return self._data[key]
        except KeyError:
            self[key]=value
            self.autosave()
            return self[key]
