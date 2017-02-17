import logging

class CollectingHandler(logging.Handler):
    instance = None

    def __init__(self):
        self.collected = []
        if self.__class__.instance is not None:
            raise RuntimeError('This is a singleton class!')
        super().__init__()
        self.__class__.instance = self

    @classmethod
    def get_default(cls):
        return cls.instance

    def emit(self, record):
        self.collected.append(record)
