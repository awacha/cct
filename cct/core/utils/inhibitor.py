class Inhibitor(object):
    """A simple counting context manager"""

    def __init__(self, callback=None):
        self._inhibited = 0
        self.callback = callback

    def __enter__(self):
        self._inhibited += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        assert self._inhibited >= 1
        self._inhibited -= 1
        if self._inhibited == 0:
            self.callback()

    @property
    def inhibited(self):
        return self._inhibited > 0
