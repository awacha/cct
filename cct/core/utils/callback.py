import itertools
from typing import Callable


class SignalFlags(object):
    RUN_FIRST = 1
    RUN_LAST = 2
    RUN_CLEANUP = 4
    NO_RECURSE = 8
    DETAILED = 16
    ACTION = 32
    NO_HOOKS = 64
    MUST_COLLECT = 128
    DEPRECATED = 256


class Callbacks(object):
    """A backend-agnostic callback mechanism, in the style of GObject.

    Signals can be specified by the __signals__ class attribute, which
    is a dictionary of tuples. The keys are the signal names (strings),
    and each tuple must have the following format:

    (<signal flags>, <return value>, <argument types>)

    where:

    <signal flags> are a combination of flags in SignalFlags. Presently
        only RUN_FIRST and RUN_LAST are implemented.
    <return value> is the value what the emit() function should return.
    <argument types> is a tuple of argument types.
    """

    __signals__ = {}

    def __init__(self):
        self._signalconnections = []
        self._nextsignalconnectionid = 0

    def connect(self, signal: str, callback: Callable, *args, **kwargs) -> int:
        """Connect a callback to a signal.

        :param signal: the name of the signal
        :type signal: str
        :param callback: the callback function
        :type callback: callable
        :return: the signal connection ID
        :rtype: int

        Other positional and keyword arguments are passed on to the
        callback function whenever the signal is emitted.
        """
        if signal not in self.__signals__:
            raise ValueError(signal)
        self._signalconnections.append({'signal': signal,
                                        'callback': callback,
                                        'args': args,
                                        'kwargs': kwargs,
                                        'id': self._nextsignalconnectionid,
                                        'blocked': 0})
        self._nextsignalconnectionid += 1
        return self._signalconnections[-1]['id']

    def disconnect(self, connectionid: int):
        """Disconnect a callback signal."""
        self._signalconnections = [s for s in self._signalconnections if s['id'] != connectionid]

    def handler_block(self, connectionid: int):
        [s_ for s_ in self._signalconnections if s_['id'] == connectionid][0]['blocked'] += 1

    def handler_unblock(self, connectionid: int):
        sc = [s_ for s_ in self._signalconnections if s_['id'] == connectionid][0]
        if sc['blocked'] <= 0:
            sc['blocked'] = 0
            raise ValueError('Cannot unblock signal handler #{:d}: not blocked.'.format(connectionid))
        sc['blocked'] -= 1

    def emit(self, signal: str, *args):
        if len(args) != len(self.__signals__[signal][2]):
            raise ValueError('Incorrect number of arguments supplied to signal {}.'.format(signal))
        for a, t, i in zip(args, self.__signals__[signal][2], itertools.count(0)):
            if not isinstance(a, t):
                raise TypeError('Argument #{:d} of signal {} is of incorrect type {}. Expected: {}.'.format(
                    i, signal, type(a), t))
        if self.__signals__[signal][0] & SignalFlags.RUN_FIRST:
            retval = self._call_default_callback(signal, *args)
            if isinstance(retval, tuple):
                assert len(retval) == 2
                done, ret = retval
            else:
                done = bool(retval)
                ret = None
            if done:
                assert isinstance(ret, self.__signals__[signal][1])
                return ret
        for s in [s_ for s_ in self._signalconnections if s_['signal'] == signal]:
            if s['blocked'] > 0:
                continue
            retval = s['callback'](self, *args, *s['args'], **s['kwargs'])
            if isinstance(retval, tuple):
                assert len(retval) == 2
                done, ret = retval
            else:
                done = bool(retval)
                ret = None
            if done:
                assert isinstance(ret, self.__signals__[signal][1])
                return ret
        if self.__signals__[signal][0] & SignalFlags.RUN_LAST:
            retval = self._call_default_callback(signal, *args)
            if isinstance(retval, tuple):
                assert len(retval) == 2
                done, ret = retval
            else:
                done = bool(retval)
                ret = None
            if done:
                assert isinstance(ret, self.__signals__[signal][1])
                return ret
        return None

    def _call_default_callback(self, signal: str, *args):
        if hasattr(self, 'do_' + signal) and callable(getattr(self, 'do_' + signal)):
            return getattr(self, 'do_' + signal)(*args)
        return None
