import multiprocessing
from typing import Optional, Any, final

from ..h5io import ProcessingH5File


class BackgroundProcessError(Exception):
    """Exception raised during the processing. Accepts a single string argument."""
    pass


class UserStopException(BackgroundProcessError):
    pass


class Results:
    time_total: float = 0
    success: bool = False
    status: str = ''


class Message:
    type_: str
    message: str
    sender: Any = None
    totalcount: Optional[int] = None
    currentcount: Optional[int] = None
    traceback: Optional[str] = None

    def __init__(self, sender: Any, type_: str, message: str, totalcount: int = None, currentcount: int = None,
                 traceback: Optional[str] = None):
        self.type_ = type_
        self.sender = sender
        self.message = message
        self.totalcount = totalcount
        self.currentcount = currentcount
        self.traceback = traceback

    def __str__(self) -> str:
        return 'Message(sender={}, type={}, totalcount={}, currentcount={}, message={}'.format(self.sender, self.type_,
                                                                                               self.totalcount,
                                                                                               self.currentcount,
                                                                                               self.message)


class BackgroundProcess:
    h5compression: Optional[str] = 'gzip'
    killSwitch: multiprocessing.Event = None
    h5io: ProcessingH5File = None
    resultsqueue: multiprocessing.Queue = None
    jobid: Any = None
    result: Results = None

    def __init__(self, jobid: Any, h5file: str, h5lock: multiprocessing.Lock,
                 killswitch: multiprocessing.Event, resultsqueue: multiprocessing.Queue,
                 ):
        self.jobid = jobid
        self.h5io = ProcessingH5File(h5file, h5lock)
        self.resultsqueue = resultsqueue
        self.killSwitch = killswitch
        self.result = Results()

    @final
    def sendProgress(self, message: str, total: Optional[int] = None,
                     current: Optional[int] = None):
        self.resultsqueue.put(
            Message(sender=self.jobid, type_='progress', message=message, totalcount=total, currentcount=current))
        if self.killSwitch.is_set():
            raise UserStopException('Stopping on user request.')

    @final
    def sendError(self, message: str, traceback: Optional[str] = None):
        self.resultsqueue.put(Message(sender=self.jobid, type_='error', message=message, traceback=traceback))

    @classmethod
    def run(cls, *args, **kwargs) -> Any:
        job = cls(*args, **kwargs)
        job.main()
        return job.result

    def main(self):
        raise NotImplementedError
