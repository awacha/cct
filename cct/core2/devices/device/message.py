import time
from typing import Any, Dict


class Message:
    timestamp: float
    command: str
    kwargs: Dict[str, Any] = None

    def __init__(self, command: str, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.timestamp = time.monotonic()

    def __getitem__(self, item):
        return self.kwargs[item]
