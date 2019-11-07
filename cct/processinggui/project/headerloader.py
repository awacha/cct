"""A mechanism to load header files in separate processes using the `multiprocessing` module """
import logging
import os
from multiprocessing import Pool
from multiprocessing.pool import AsyncResult
from typing import Sequence, List, Optional, Tuple

from PyQt5 import QtCore
from sastool.io.credo_cct import Header

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def loadHeader(fsn:int, dirs:Sequence[str], headerfileformat:str) -> Tuple[int, Optional[Header]]:
    for d in dirs:
        try:
            return (fsn, Header.new_from_file(os.path.join(d, headerfileformat.format(fsn))))
        except FileNotFoundError:
            continue
    return (fsn, None)

class HeaderLoader(QtCore.QObject):
    TIMERINTERVAL: int=100 # milliseconds
    pool: Optional[Pool]
    outstanding: List[AsyncResult]
    timer: QtCore.QTimer
    fsns: Sequence[int]
    dirs: Sequence[str]
    headerfileformat: str
    results: List[Tuple[int, Optional[Header]]]
    finished = QtCore.pyqtSignal() # loading finished.
    progress = QtCore.pyqtSignal(int, int) # total count, ready count
    timerid:int=0

    def __init__(self, fsns:Sequence[int], dirs:Sequence[str], headerfileformat:str):
        super().__init__()
        self.pool=None # do not create a pool yet
        self.outstanding = []
        self.timer = QtCore.QTimer(self)
        self.fsns=fsns
        self.dirs=dirs
        self.headerfileformat=headerfileformat
        self.results=[]

    def submit(self):
        self.pool=Pool()
        self.results=[]
        self.outstanding = [self.pool.apply_async(loadHeader, [f, self.dirs, self.headerfileformat]) for f in self.fsns]
        self.timerid=self.startTimer(self.TIMERINTERVAL)
        self.progress.emit(len(self.fsns), 0)

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        ready = [o for o in self.outstanding if o.ready()] # select those which are ready
        if (not ready) and (self.outstanding):
            # do not block the event loop
            event.accept()
            return
        self.results.extend([r.get() for r in ready])
        self.outstanding = [o for o in self.outstanding if o not in ready]
        self.progress.emit(len(self.fsns), len(self.results))
        if not self.outstanding:
            # we have finished
            self.pool.close()
            self.pool.join()
            self.pool=None
            self.killTimer(self.timerid)
            self.finished.emit()
        event.accept()

    def stop(self):
        self.pool.terminate()
        self.outstanding = []

    def isRunning(self) -> bool:
        return bool(self.outstanding) or (self.pool is not None)

    def headers(self) -> List[Header]:
        return sorted([header for fsn, header in self.results if header is not None], key=lambda h:h.fsn)
