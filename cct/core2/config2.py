import itertools
import pickle
import logging
import shutil
from typing import Any, Tuple, Union, Dict, Optional

from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

KeyType = Tuple[Union[str, int], ...]


class Config(QtCore.QAbstractItemModel):
    """Second-generation configuration store

    In contrast to the previous implementation, the hierarchical configuration tree is stored in a single,
    flat dictionary with tuples as keys, contained in a single Config instance, instead of a hierarchy of
    several instances, which resulted in an uncontrollable, memory-leaking state, due to object lifetime
    quirks in Qt and Python. On the other hand, this makes access to config from the code a bit unwieldy.

    This Config class implements the QAbstractItemModel interface, permitting it to be used as a TreeView
    model for easy config editing.

    The Python dict interface is also implemented (note some differences). Keys are arbitrary length
    tuples of strings and ints. As a special case, ints and strings are also accepted, as a simple means to
    reference top-level items. Thus the following works as expected:

    # >>> config['string1'] = 'value'
    # >>> config['string1', 2] = 'value'
    # >>> config[('string1', 2)] = 'value'    # works but the parentheses are not required

    To get the keys, values or (key, value) pairs as in Python dicts, the methods `keysAt()`, `valuesAt()`
    and `itemsAt()` are implemented. Their single argument is a key tuple, indicating a top level, whose
    immediate children are to be listed.
    """

    class SubTreePlaceHolder:
        pass

    _data: Dict[KeyType, Any]
    changed = Signal(object, object, name='changed')
    autosave_interval: float = 0.5
    _autosave_timer: Optional[int] = None
    filename: Optional[str] = None
    
    def __init__(self, filename: Optional[str] = None, parent: QtCore.QObject = None, autosave: bool=True):
        self._data = {(): Config.SubTreePlaceHolder}
        super().__init__(parent)
        if filename is not None:
            self.load(filename)
        if not autosave:
            self.autosave_interval = None
        self.changed.connect(self.onChanged)

    ## Re-implemented QAbstractItemModel methods

    def columnCount(self, parent: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex] = ...) -> int:
        return 2

    def rowCount(self, parent: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex] = ...) -> int:
        return len([key for key in self._data if key[:-1] == parent.internalPointer()])

    def data(self, index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex], role: int = ...) -> Any:
        key = self._index2key(index)
        if (index.column() == 0) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return key[-1]
        elif (index.column() == 1) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return str(self._data[key])
        elif (index.column() == 1) and (role == QtCore.Qt.ItemDataRole.EditRole):
            return self._data[key]

    def parent(self, index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex]) -> QtCore.QObject:
        return self._key2index(self._parentkey(index.internalPointer()))
    
    def index(self, row: int, column: int, parent: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex] = ...) -> QtCore.QModelIndex:
        if not parent.isValid():
            # we are dealing with a first-level item
            return self.createIndex(row, column, sorted([key for key in self._data if len(key) == 1])[row])
        else:
            parentkey: KeyType = parent.internalPointer()
            children = sorted([key for key in self._data.keys() if key[:-1] == parentkey])
            return self.createIndex(row, column, children[row])
    
    def flags(self, index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex]) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable
    
    def setData(self, index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex], value: Any, role: int = ...) -> bool:
        if index.column() == 0:
            # cannot set the key
            return False
        elif (index.column() == 1) and (role == QtCore.Qt.ItemDataRole.EditRole):
            self._data[self._index2key(index)] = value
            return True
        else:
            return False
    
    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Orientation.Horizontal) and (role == QtCore.Qt.ItemDataRole.DisplayRole):
            return ['Key', 'Value'][section]

    ## Data access interface to make this similar to a Python dict

    def __contains__(self, item: Union[KeyType, int, str]) -> bool:
        if isinstance(item, (str, int)):
            # make a tuple from a scalar
            item = (item, )
        return item in self._data

    def __getitem__(self, key: Union[KeyType, int, str]) -> Any:
        if isinstance(key, (int, str)):
            # normalize the index to tuple if it is scalar
            key = (key,)
        if (not key) or (self._data[key] is self.SubTreePlaceHolder):
            # this is a subtree, return a dictionary
            childkeys = self._childkeys(key)
            dic = {}
            for childkey in childkeys:
                dic[childkey[-1]] = self[childkey]
            return dic
        else:
            # a simple scalar entry
            if self._childkeys(key):
                logger.critical(f'Config entry {key} should be a scalar (value is {self._data[key]}, of type {type(self._data[key])}, but it has some children: {self._childkeys(key)}')
                assert not self._childkeys(key)
            return self._data[key]

    def __delitem__(self, key: Union[KeyType, int, str]):
        if isinstance(key, (int, str)):
            # normalize the index to tuple if it is scalar
            key = (key,)
        if not key:
            raise ValueError('Cannot delete the root item')
        # now we can remove the key, notifying Qt in turn.
        index = self._key2index(key)
        self.beginRemoveRows(self.parent(index), index.row(), index.row())
        for key_ in list(self._data.keys()):
            if key_[:len(key)] == key:
                del self._data[key_]
        self.endRemoveRows()
        # emit a changed signal on the parent key
        self.changed.emit(self._parentkey(key), self[self._parentkey(key)])

    def __setitem__(self, key: Union[KeyType, int, str], value: Any):
        if isinstance(key, (int, str)):
            # normalize the index to tuple if it is scalar
            key = (key,)
        if isinstance(value, dict):
            # If a dict is to be inserted, insert the whole subtree recursively
            self.updateAt(key, value, delete_missing=True)
        elif key not in self._data:
            # first ensure that the parents are there
            for i in range(1, len(key)):
                if key[:i] not in self:
                    self[key[:i]] = self.SubTreePlaceHolder
            # we will need to notify the Qt Model on the insertion of a new row
            parent = self._key2index(self._parentkey(key))

            # first add it, then get its index. This is not thread-safe, but it is easier to get the row number.
            self._data[key] = value
            row = self._siblingkeys(key).index(key)
            self.beginInsertRows(parent, row, row)
            self.endInsertRows()
            self.changed.emit(key, self._data[key])
            self.changed.emit(self._parentkey(key), self._data[self._parentkey(key)])
        elif self._data[key] != value:
            # a simple value change of an existing key
            self._data[key] = value
            self.changed.emit(key, self._data[key])
        else:
            pass  # key is already there and the value also matches

    def __iter__(self):
        for key, value in self._data:
            yield key, value

    ## Some convenience functions for internal use

    def _get_keytuple(self, key: KeyType) -> KeyType:
        candidates = [key_ for key_ in self._data.keys() if key_ == key]
        if len(candidates) == 0:
            raise KeyError(key)
        elif len(candidates) > 1:
            raise ValueError(f'Inconsistency in Config: multiple keys correspond to {key}')
        else:
            assert len(candidates) == 1
            return candidates[0]

    def _key2index(self, key: KeyType) -> QtCore.QModelIndex:
        if len(key) == 0:
            # this is the root element
            return QtCore.QModelIndex()
#        elif len(key) == 1:
#            row = sorted({key_[0] for key_ in self._data}).index(key[0])
#            return self.createIndex(row, 0, self._get_keytuple(key))
        else:
            try:
                row = self._siblingkeys(key).index(key)
            except ValueError:
                raise KeyError(key)
            return self.createIndex(row, 0, self._get_keytuple(key))

    def _index2key(self, index: Union[QtCore.QModelIndex, QtCore.QPersistentModelIndex]) -> KeyType:
        return self._get_keytuple(index.internalPointer())

    def _parentkey(self, key: KeyType):
        if not key:
            raise ValueError('The root key does not have a parent')
        return key[:-1]

    def _siblingkeys(self, key: KeyType):
        if not key:
            return []
        return sorted([key_ for key_ in self._data.keys() if key_[:-1] == key[:-1]], key=self._sort_keyfcn)

    def _childkeys(self, key: KeyType):
        if not key:
            return sorted([key_ for key_ in self._data if len(key_) == 1])
        return sorted([key_ for key_ in self._data.keys() if key_[:-1] == key], key=self._sort_keyfcn)

    def _sort_keyfcn(self, key: KeyType):
        return tuple([(0 if isinstance(k, int) else 1, k) for k in key])

    ## Load and save

    def load(self, filename: str, update: bool=True, autosave: bool=True):
        """
        :param filename:
        :param update:
        :param autosave:
        """
        with open(filename, 'rb') as f:
            data = pickle.load(f)
        if isinstance(data, tuple) and (len(data) == 2) and (data[0] == 'CCT config'):
            if update:
                for key, value in data[1]:
                    self[key] = value
            else:
                self.beginResetModel()
                self._data = data[1]
                self.endResetModel()
        elif isinstance(data, dict):
            if not update:
                self.__setstate__(data)
            else:
                self.updateAt((), data)
            # make a backup copy of the old format file.
            shutil.copy2(filename, filename+'.oldformat')
        if autosave:
            self.filename = filename
        logger.debug(f'Loaded config from file {filename}')

    def __setstate__(self, state):
        if isinstance(state, tuple) and (len(state) == 2) and state[0] == 'CCT config':
            self.beginResetModel()
            self._data = state[1]
            self.endResetModel()
        elif isinstance(state, dict):
            self.beginResetModel()
            self[()] = state
            self.endResetModel()

    def __getstate__(self):
        return self.toDict(())

    def toDict(self, rootkey: KeyType=()) -> Dict[Union[str, int], Any]:
        dic = {}
        for key, value in self.itemsAt(rootkey):
            subkeys = self.keysAt(rootkey+(key,))
            if not subkeys:
                dic[key] = value
            else:
                dic[key] = self.toDict(rootkey + (key,))
        return dic

    def save(self, filename: Optional[str] = None):
        if filename is None:
            filename = self.filename
        if filename is None:
            raise ValueError('File name not given.')
        logger.info(f'Saving config to file {filename}.')
        with open(filename, 'wb') as f:
            pickle.dump(('CCT config', self._data), f)

    def updateAt(self, root: KeyType, dic: Dict[Union[str, int], Any], delete_missing=False):
        self[root] = Config.SubTreePlaceHolder
        for key in self.keysAt(root):
            if key not in dic:
                del self[root + (key,)]
        for key, value in dic.items():
            if isinstance(value, dict):
                self.updateAt(root+(key,), value)
            else:
                self[root+(key,)] = value

    def keysAt(self, *root: Union[KeyType, int, str]):
        rootkey = tuple(itertools.chain(*[(r,) if isinstance(r, (str, int)) else r for r in root]))
        return [key[-1] for key in self._childkeys(rootkey)]

    def valuesAt(self, *root: Union[KeyType, int, str]):
        rootkey = tuple(itertools.chain(*[(r,) if isinstance(r, (str, int)) else r for r in root]))
        return [self[key] for key in self._childkeys(rootkey)]

    def itemsAt(self, *root: Union[KeyType, int, str]):
        rootkey = tuple(itertools.chain(*[(r,) if isinstance(r, (str, int)) else r for r in root]))
        return [(key[-1], self[key]) for key in self._childkeys(rootkey)]

    def setdefault(self, key: KeyType, defaultvalue: Any) -> Any:
        try:
            return self[key]
        except KeyError:
            self[key] = defaultvalue
            return self[key]

    def _autosave(self):
        if (self.autosave_interval is None) or (self.filename is None):
            return
        if self._autosave_timer is not None:
            self.killTimer(self._autosave_timer)
        self._autosave_timer = self.startTimer(int(self.autosave_interval*1000), QtCore.Qt.TimerType.PreciseTimer)

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        if event.timerId() == self._autosave_timer:
            self.save(self.filename)
            self.killTimer(self._autosave_timer)
            self._autosave_timer = None

    @Slot(object, object)
    def onChanged(self, key: KeyType, value: Any):
        self._autosave()
