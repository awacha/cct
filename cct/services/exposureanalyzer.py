import multiprocessing
import queue
from gi.repository import GLib
from .service import Service


class ExposureAnalyzer(Service):

    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._backendprocess = multiprocessing.Process(
            target=self._backgroundworker, daemon=True)
        self._queue_to_backend = multiprocessing.Queue()
        self._queue_to_frontend = multiprocessing.Queue()
        self._handler = GLib.idle_add(self._idle_function)

    def _backgroundworker(self):
        pass

    def _idle_function(self):
        try:
            resulttype, result = self._queue_to_frontend.get_nowait()
        except queue.Empty:
            return True

    def submit(self, prefix, fsn):
        self._queue_to_backend.put_nowait((prefix, fsn))