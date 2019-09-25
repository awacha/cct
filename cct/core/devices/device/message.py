import operator
import time


class Message(object):
    """A simple message object which can be passed between processes through queues. For debugging purposes the number
    of instances is kept."""
    instances = 0

    def __new__(cls, *args, **kwargs):
        cls.instances += 1
        obj = object.__new__(cls)
        return obj

    def __init__(self, messagetype, messageid, sender, **kwargs):
        self._dict = {'type': messagetype, 'id': messageid, 'sender': sender, 'timestamp': time.monotonic()}
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

    def __contains__(self, key):
        return key in self._dict