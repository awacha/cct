class Inhibitor(object):
    """A simple counting context manager"""

    def __init__(self, callback=None, max_inhibit = 1):
        self._inhibited = 0
        self.callback = callback
        self._max_inhibit = max_inhibit

    def __enter__(self):
        if self._inhibited >= self._max_inhibit:
            raise ValueError('Maximum number of inhibitions reached.')
        self._inhibited += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        assert self._inhibited >= 1
        self._inhibited -= 1
        if self._inhibited == 0:
            self.callback()

    @property
    def inhibited(self):
        return self._inhibited > 0

    @property
    def n_inhibited(self):
        return self._inhibited

    def __bool__(self):
        return self.inhibited