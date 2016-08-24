import operator
import time


class Message(object):
    instances = 0

    def __new__(cls, *args, **kwargs):
        cls.instances += 1
        obj = object.__new__(cls)
        return obj

    def __init__(self, type, id, sender, **kwargs):
        self._dict = {'type': type, 'id': id, 'sender': sender, 'timestamp': time.monotonic()}
        self._dict.update(kwargs)

    def __getitem__(self, item):
        return operator.getitem(self._dict, item)

    def __setitem__(self, key, value):
        return operator.setitem(self._dict, key, value)

    def __delitem__(self, key):
        return operator.delitem(self._dict, key)

    def __del__(self):
        self._dict = None
        self.__class__.instances -= 1
