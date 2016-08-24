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
        self.__signalhandles = []
        self._nextsignalconnectionid = 0

    @classmethod
    def _get_signal_description(cls, name):
        if name in cls.__signals__:
            return cls.__signals__[name]
        else:
            for bcls in cls.__bases__:
                try:
                    return bcls._get_signal_description(name)
                except AttributeError:
                    pass
            raise ValueError(name)

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
        self._get_signal_description(signal)
        self.__signalhandles.append({'signal': signal,
                                     'callback': callback,
                                     'args': args,
                                     'kwargs': kwargs,
                                     'id': self._nextsignalconnectionid,
                                     'blocked': 0})
        self._nextsignalconnectionid += 1
        return self.__signalhandles[-1]['id']

    def disconnect(self, connectionid: int):
        """Disconnect a callback signal."""
        self.__signalhandles = [s for s in self.__signalhandles if s['id'] != connectionid]

    def handler_block(self, connectionid: int):
        for s_ in self.__signalhandles:
            assert isinstance(s_, dict)
        [s_ for s_ in self.__signalhandles if s_['id'] == connectionid][0]['blocked'] += 1

    def handler_unblock(self, connectionid: int):
        for s_ in self.__signalhandles:
            assert isinstance(s_, dict)
        sc = [s_ for s_ in self.__signalhandles if s_['id'] == connectionid][0]
        assert isinstance(sc, dict)
        if sc['blocked'] <= 0:
            sc['blocked'] = 0
            raise ValueError('Cannot unblock signal handler #{:d}: not blocked.'.format(connectionid))
        sc['blocked'] -= 1

    def emit(self, signal: str, *args):
        sigdesc = self._get_signal_description(signal)
        if len(args) != len(sigdesc[2]):
            raise ValueError('Incorrect number of arguments supplied to signal {}.'.format(signal))
        for a, t, i in zip(args, sigdesc[2], itertools.count(0)):
            if not isinstance(a, (t, type(None))):
                raise TypeError('Argument #{:d} of signal {} is of incorrect type {}. Expected: {} or None.'.format(
                    i, signal, type(a), t))
        if sigdesc[0] & SignalFlags.RUN_FIRST:
            retval = self._call_default_callback(signal, *args)
            if isinstance(retval, tuple):
                assert len(retval) == 2
                done, ret = retval
            else:
                done = bool(retval)
                ret = None
            if done:
                assert isinstance(ret, sigdesc[1])
                return ret
        for s_ in self.__signalhandles:
            assert isinstance(s_, dict)
        for s in self.__signalhandles:
            assert isinstance(s, dict)
            if (s['signal'] != signal) or (s['blocked'] > 0):
                continue
            retval = s['callback'](self, *(args + s['args']), **s['kwargs'])
            if isinstance(retval, tuple):
                assert len(retval) == 2
                done, ret = retval
            else:
                done = bool(retval)
                ret = None
            if done:
                if sigdesc[1] is not None:
                    assert isinstance(ret, sigdesc[1])
                return ret
        if sigdesc[0] & SignalFlags.RUN_LAST:
            retval = self._call_default_callback(signal, *args)
            if isinstance(retval, tuple):
                assert len(retval) == 2
                done, ret = retval
            else:
                done = bool(retval)
                ret = None
            if done:
                assert isinstance(ret, sigdesc[1])
                return ret
        return None

    def _call_default_callback(self, signal: str, *args):
        if hasattr(self, 'do_' + signal) and callable(getattr(self, 'do_' + signal)):
            return getattr(self, 'do_' + signal)(*args)
        return None
