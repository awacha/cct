from .backgroundprocess import BackgroundProcess
import multiprocessing
from multiprocessing import Lock
from typing import Any, Union, Optional
import enum
from .resultsentry import CorMatFileType, CurveFileType, PatternFileType, SampleDistanceEntry

class ReportFileType(enum.Enum):
    DOCX = ('Microsoft(R) Word(TM) document', '*.docx')
    XLSX = ('Microsoft(R) Excel(TM) workbook', '*.xlsx')


class ReportingJob(BackgroundProcess):
    filetype: Union[CorMatFileType, CurveFileType, PatternFileType, ReportFileType]
    samplename: Optional[str]
    distkey: Optional[str]
    path: str

    def __init__(self, jobid: Any, h5file: str, h5lock: Lock,
                 stopEvent: multiprocessing.synchronize.Event, messagequeue: multiprocessing.queues.Queue,
                 filetype: Union[CorMatFileType, CurveFileType, PatternFileType, ReportFileType],
                 samplename: Optional[str], distkey: Optional[str], path: str):
        super().__init__(jobid, h5file, h5lock, stopEvent, messagequeue)
        self.filetype = filetype
        self.samplename = samplename
        self.distkey = distkey
        self.path = path

    def main(self):
        if (self.samplename is not None) and (self.distkey is not None):
            item = SampleDistanceEntry(self.samplename, self.distkey, self.h5io)
            if isinstance(self.filetype, CorMatFileType):
                item.writeCorMat(self.path, self.filetype)
            elif isinstance(self.filetype, PatternFileType):
                item.writePattern(self.path, self.filetype)
            elif isinstance(self.filetype, CurveFileType):
                item.writeCurve(self.path, self.filetype)
            else:
                assert False
        else:
            # either samplename or distkey is None: export all samples
            pass
