import gc
import logging
import os
import pathlib
import pickle
import random
import textwrap
import time
import weakref
import functools
from typing import Dict, Any, Union, Tuple, KeysView, ValuesView, ItemsView, Optional, List

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

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

    # The `changed` signal is emitted whenever the value of a key changes. Its arguments: the path (tuple of strings)
    # and the new value (any type)
    changed = Signal(object, object)

    # The name of the associated config file. If not None, any change is written almost instantly.
    filename: Optional[str] = None
    _data: Dict[str, Any]
    _modificationcount: int = 0
    _autosavetimeout: float = 0.1
    _autosavetimer: Optional[int] = None
    instances: List["Config"] = []
    path: str
    _name: str

    def __init__(self, dicorfile: Union[None, Dict[str, Any], str] = None, parent: Optional["Config"]=None, path: Optional[str] = None):
        """Initialize a new Config instance

        :param dicorfile: the file name to load the configuration from, or a dictionary-like object
        :type dicorfile: str or dict or None
        """
        Config.instances.append(weakref.proxy(self))
        self._name = f"Config({path})_{time.monotonic_ns()}_{random.random()}"
        self.path = path
        super().__init__(parent)
        self.setObjectName(self._name)
        logger.debug(f'Creating a Config object with path {path}: number of active Config instances is {len(Config.instances)}')
        self.destroyed.connect(functools.partial(Config.onDestroyed, self.__dict__))
        self._data = {}
        if dicorfile is None:
            # no initialization required
            pass
        elif isinstance(dicorfile, dict):
            self.__setstate__(dicorfile)
        elif isinstance(dicorfile, str):
            self.load(dicorfile, update=False)
        self.changed.connect(self.onChanged)

    @Slot(QtCore.QObject, name='onDestroyed')
    @staticmethod
    def onDestroyed(selfdict):
        newinstances = []
        removedcount = 0
        vanishedPython = 0
        for obj in Config.instances:
            try:
                if obj._name == selfdict['_name']:
                    removedcount += 1
                    continue
            except ReferenceError:
                vanishedPython += 1
                continue
            newinstances.append(obj)

        Config.instances = newinstances

        try:
            assert removedcount <= 1
            assert removedcount > 0
        except AssertionError:
#            print(f'{selfdict["_name"]}, {selfdict["path"]}')
#            print(sorted([c._name for c in Config.instances]))
            pass
        logger.debug(f'Destroying a Config object ({selfdict["path"]}): number of active Config instances is {len(Config.instances)}, stale weakref: {vanishedPython}')
        for c in Config.instances[:]:
            try:
                c.objectName()
            except RuntimeError:
                assert False

    def autosave(self):
        """Request automatic saving of the config.

        Changes are not saved instantly. Instead, a timer of `self._autosavetimeout` seconds is started. Changes
        in this interval are accumulated, to avoid too frequent disk writes.
        """
        if self.filename is not None:
            # only save data if we have a file name
            if self._autosavetimer is not None:
                # a timer is already running, restart it.
                self.killTimer(self._autosavetimer)
                self._autosavetimer = None
            # start a timer. After the required time interval has elapsed, do the actual saving.
            self._autosavetimer = self.startTimer(int(self._autosavetimeout * 1000), QtCore.Qt.TimerType.PreciseTimer)

    def timerEvent(self, timerEvent: QtCore.QTimerEvent) -> None:
        if timerEvent.timerId() == self._autosavetimer:
            # do autosave
            self.killTimer(timerEvent.timerId())
            self._autosavetimer = None
            logger.debug('Autosave timer elapsed, saving.')
            self.save(self.filename)

    @Slot(object, object)
    def onChanged(self, path: Tuple[str, ...], value: Any):
        """Whenever something changes, request automatic save."""
        self.autosave()

    def __setitem__(self, key: Union[int, str, Tuple[Union[str, int], ...]], value: Any):
        """Modify (or create) a new key->value pair using the dict['key'] = value syntax.

        This mimics the behavior of the common Pythonic dict, with a few differences:

        - if `key` is a string or an integer, the behaviour is the same as the dict.
        - `key` can be a tuple of strings, corresponding to a path in the Config hierarchy.
            In this case, the job is delegated to the corresponding sub-Config instances
            below, i.e.:
            >>> config[('key1', 'key2')] = newvalue

            is equivalent to
            >>> config['key1']['key2'] = newvalue

            It is also checked (with an assertion) that config['key1'] is also a Config instance.

            The special case of
            >>> config[('key1', )] = newvalue

            is equivalent to
            >>> config['key1'] = newvalue

            Supplying a 0-length tuple is an error.
        - Other key types than int, str, tuple() are not supported.

        Some value types are stored in a special way:

        - If the value is a dict, a sub-Config is created and updated key-by-key. This enforces the creation
            of a whole Config hierarchy in the case of nested dicts.

        """
#        logger.debug(f'Config.__setitem__({key}, {value})')
        if isinstance(key, tuple) and len(key) > 1:
            subconfig = self._data[key[0]]
            assert isinstance(subconfig, Config)
            return subconfig.__setitem__(key[1:], value)
        elif isinstance(key, tuple) and len(key) == 1:
            key = key[0]
        elif isinstance(key, tuple) and len(key) == 0:
            raise ValueError('Empty tuples cannot be Config keys!')
        elif not isinstance(key, (str, int)):
            raise ValueError(f'Invalid key type: {key}, {type(key)}')

        if isinstance(value, Config):
            if key not in self._data:
                value = Config(value.asdict(), path=f'{self.path}/{key}', parent=self)
                self._data[key] = value
                value.changed.connect(self._subConfigChanged)
                self.changed.emit((key,), value)
            elif self._data[key] is value:
                return  # physically the same Config instance
            else:
                if isinstance(self[key], Config):
                    self[key].deleteLater()
                del self[key]  # this takes care of all cases, even when the previous value is a Config
                self[key] = value  # try again
        elif isinstance(value, dict):
            # create a Config from that dictionary
            cfg = Config(value, path=f'{self.path}/{key}', parent=self)
            self[key] = cfg  # try again
        else:
            # "ordinary" value type, i.e. not dict and not Config
            if key not in self._data:
                # nonexistent key, add it in a straightforward fashion.
                self._data[key] = value
                self.changed.emit((key,), value)
            elif isinstance(self._data[key], Config):
                # updating a Config with a non-config value: we need to disconnect the signal first
                del self[key]
                self[key] = value  # try again
            elif not (isinstance(self._data[key], type(value)) and (self._data[key] == value)):
                # the key is already present but either the type or the value is different
                del self[key]
                self._data[key] = value
                # value changed, emit the signal
#                logger.debug(f'Key value changed, emitting change signal.')
                self.changed.emit((key,), value)
            else:
                # the key is already present and both the type and value are the same. Nothing needs to be done.
                pass
        self.autosave()

    def __delitem__(self, key: Union[int, str, Tuple[Union[str, int], ...]]):
        """Delete a key->value pair from this Config, invoked by `del config[key]`

        This mimics the corresponding method of the Python dict, except that only ints,
        strings and tuples of ints/strings can be keys. If the key to be deleted is a tuple,
        the deletion request is propagated to the bottom.
        """
#        logger.debug(f'Deleting key {key}')
        if isinstance(key, (int, str)):
            key = (key,)
#        logger.debug(f'Key normalized to {key}')
        if not isinstance(key, tuple):
            raise ValueError(f'Invalid key type: {type(key)}')
        if len(key) == 0:
            raise ValueError(f'An empty tuple cannot be a key')
        elif len(key) > 1:
            # delegate the deletion to a subConfig one level below us in the hierarchy
            if not isinstance(self._data[key[0]], Config):
                raise ValueError(f'Invalid path in key {key}')
            del self._data[key[0]][key[1:]]
        else:
            assert len(key) == 1
            if isinstance(self._data[key[0]], Config):
                # deleting a sub-config. Disconnect the changed signal first.
                # Update: disconnecting the changed signal is not needed, automatically done by Qt
#                logger.debug(f'Disconnecting changed signal from {self._data[key[0]].path} to {self.path}')
#                try:
#                    self._data[key[0]].changed.disconnect(self._subConfigChanged)
#                except TypeError:
#                    pass
                try:
                    self._data[key[0]].deleteLater()
                except (RuntimeError, TypeError):
                    # sometimes the underlying C/C++ object vanishes first. Why???
                    logger.error(f'Vanished C/C++ object: {self._data[key[0]]._name}')
                    pass
            del self._data[key[0]]
        self.autosave()

    def __getitem__(self, item: Union[str, int, Tuple[Union[str, int], ...]]):
        """Respond to the `config[item]` command.
        """
        if isinstance(item, (str, int)):
            retval = self._data[item]
        elif isinstance(item, tuple):
            if len(item) == 0:
                raise ValueError('An empty tuple cannot be a Config key')
            elif len(item) == 1:
                retval = self._data[item[0]]
            else:
                return self._data[item[0]][item[1:]]
        else:
            raise ValueError(f'Invalid key type: {type(item)}')
        if isinstance(retval, Config):
            return weakref.proxy(retval)
        return retval

    def __getstate__(self) -> Dict[Union[str, int], Any]:
        """Convert the whole Config hierarchy to a dict"""
        dic = {}
        for key, value in self.items():
            if isinstance(value, Config):
                dic[key] = value.__getstate__()
            else:
                dic[key] = value
        return dic

    def keys(self) -> KeysView:
        return self._data.keys()

    def values(self) -> ValuesView:
        return self._data.values()

    def items(self) -> ItemsView:
        return self._data.items()

    @Slot(object, object)
    def _subConfigChanged(self, path: Tuple[Union[str, int], ...], newvalue: Any):
        """Slot for reacting to changes in sub-configs."""
        cnf = self.sender()
        # find the key for this `Config` instance
        try:
            key = [k for k in self.keys() if self._data[k] is cnf][0]
        except IndexError:
            # this `Config` instance does not belong to us, disconnect the signal.
            logger.warning(f'Disconnecting stale `changed` signal handler. Keys in stale config: {list(cnf.keys())}')
            try:
                cnf.changed.disconnect(self._subConfigChanged)
            except (RuntimeError, TypeError):
                pass
        else:
            # extend the path with the key and re-emit the signal.
#            logger.debug(
#                f'Config change in subconfig "{key}", path {path}. Emitting `changed` signal with path "{key}"')
            self.changed.emit((key,) + path, newvalue)
        self.autosave()

    def update(self, other: Union["Config", Dict]):
        """Mimic the .update() method of the Pythonic dict.

        Extend the current Config instance with all keys in the other one (either dict or Config), where either the key
        is nonexistent in this, or the value is different (type or value).
        """
        if self is other:
            # Nothing needs to be done
            return
        if not isinstance(other, (Config, dict)):
            raise ValueError(f'Cannot update a Config from other than another Config or a dict.')
        for key, value in other.items():
#            logger.debug(f'Updating {key=}')
            if isinstance(value, (Config, dict)) and (key in self._data):
                # we need to work hierarchically
                if self._data[key] is value:
                    # nothing needs to be done
                    pass
                # propagate down in the hierarchy
#                logger.debug(f'Delegating update work of key {key} to value {value}')
                self._data[key].update(value)
            else:
                # the value is not a Config/dict, or it is, but the key is not yet present:
                # we use __setitem__() and it will take care of everything else,
                # including disconnecting the changed() signal if the previous value is a Config.
                self[key] = value
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

    def load(self, picklefile: PathLike, update: bool = True, autosave: bool=True):
        """Load the config from a pickle.

        This also sets the `filename` attribute, i.e. autosaving will be enabled.

        :param picklefile: file name of the pickle file to be loaded
        :type picklefile: PathLike
        :param update: if True, the already existing config data will only be updated, not overwritten
        :type update: bool
        :param autosave: if True, this sets the `filename` attribute, so changes will be saved back automatically
        :type autosave: bool
        """
        if autosave:
            self.filename = picklefile
        if not update:
            logger.info(f'Loading configuration from {picklefile}')
            with open(picklefile, 'rb') as f:
                data = pickle.load(f)
#            logger.debug('Loaded a pickle file')
            self.__setstate__(data)
        else:
            logger.info(f'Loading configuration with update')
            other = Config(picklefile, path='<TEMPORARY>', parent=None)
            self.update(other)
            other.deleteLater()
            del other
            gc.collect()
#        logger.info(f'Loaded configuration from {picklefile} {"with update" if update else "clobbering"}')
#        logger.info(self.toTree())

    def save(self, picklefile: Optional[PathLike] = None):
        """Save the config to a pickle."""
        if picklefile is None:
            picklefile = self.filename
        # logger.debug(f'Saving configuration to {picklefile}')
        dirs, filename = os.path.split(picklefile)
        os.makedirs(dirs, exist_ok=True)
        with open(picklefile, 'wb') as f:
            pickle.dump(self.__getstate__(), f)
        logger.info(f'Saved configuration to {picklefile}')

        newinstances = []
        allpaths = []
        for instance in Config.instances:
            try:
                allpaths.append(instance.path)
                newinstances.append(instance)
            except ReferenceError:
                continue
        Config.instances = newinstances
#        for path in {instance.path for instance in Config.instances}:
#            if allpaths.count(path) > 1:
#                logger.warning(f'Multiple extant Config entries of path {path}: count is {allpaths.count(path)}')

    def __setstate__(self, dic: Dict[Union[str, int], Any]):
        """Convert a dictionary to a Config instance"""
        for key in self._data:
            if isinstance(self._data[key], Config):
                self._data[key].deleteLater()
            del self._data[key]
        self._data = {}
        for key, value in dic.items():
            if isinstance(value, dict):
                cfg = Config(value, path=f'{self.path}/{key}', parent=self)
                self[key] = cfg
            else:
                self[key] = value

    asdict = __getstate__

    def __str__(self):
        return str(self.__getstate__())

    def __repr__(self):
        return repr(self.__getstate__())

    def __len__(self):
        return len(self._data)

    def setdefault(self, key: Union[str, int, Tuple[Union[str, int], ...]], value: Any) -> Any:
        try:
            return self[key]
        except KeyError:
            self[key] = value
            return self[key]

    def __del__(self):
        self.filename = None
#        logger.debug(f'Config.__del__ called, requesting deleteLater() on config {self.path}')
        self.deleteLater()

    def deleteLater(self) -> None:
        self.filename = None
#        try:
#            self.changed.disconnect(self.onChanged)
#        except (TypeError, RuntimeError):
#            pass
        #print(f'Config(path={self.path}).deleteLater() called')
        for key in list(self.keys()):
            if isinstance(self[key], Config):
                #print(f'Deleting subkey {key}')
                self[key].deleteLater()
                del self[key]  # this calls self[key].deleteLater(), too
        try:
            super().deleteLater()
        except RuntimeError:
            pass

    def toTree(self) -> str:
        treestr = ""
        for key in self:
            if isinstance(self[key], Config):
                treestr += f'{key}  ({self[key].path})\n'
                treestr += textwrap.indent(self[key].toTree(), ' ')
        return treestr
