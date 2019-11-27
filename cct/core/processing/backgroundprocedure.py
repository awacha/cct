import multiprocessing
from typing import Optional, Any


class ProcessingError(Exception):
    """Exception raised during the processing. Accepts a single string argument."""
    pass


class UserStopException(ProcessingError):
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


class BackgroundProcedure:
    h5compression: Optional[str] = 'gzip'
    killSwitch: multiprocessing.Event = None
    h5WriterLock: multiprocessing.Lock = None
    h5file: str = None
    resultsqueue: multiprocessing.Queue = None
    jobid: Any = None
    result: Results = None

    def __init__(self, jobid: Any, h5writerLock: multiprocessing.Lock, killswitch: multiprocessing.Event,
                 resultsqueue: multiprocessing.Queue,  h5file: str,
                 ):
        self.jobid = jobid
        self.h5file = h5file
        self.resultsqueue = resultsqueue
        self.killSwitch = killswitch
        self.h5WriterLock = h5writerLock
        self.result = Results()

    def sendProgress(self, message: str, total: Optional[int] = None,
                     current: Optional[int] = None):
        self.resultsqueue.put(
            Message(sender=self.jobid, type_='progress', message=message, totalcount=total, currentcount=current))
        if self.killSwitch.is_set():
            raise UserStopException('Stopping on user request.')

    def sendError(self, message: str, traceback: Optional[str] = None):
        self.resultsqueue.put(Message(sender=self.jobid, type_='error', message=message, traceback=traceback))

    @classmethod
    def run(cls, jobid: Any, h5writerLock: multiprocessing.Lock, killswitch: multiprocessing.Event,
            resultsqueue: multiprocessing.Queue, h5file: str, **kwargs) -> Any:
        job = cls(jobid=jobid, h5writerLock=h5writerLock,
                  killswitch=killswitch,
                  resultsqueue=resultsqueue,
                  h5file=h5file, **kwargs)
        job._execute()
        return job.result

