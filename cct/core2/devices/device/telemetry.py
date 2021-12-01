import os
import time
import datetime
from typing import List, NamedTuple, Dict, Tuple, Final, Optional
from collections import namedtuple
import textwrap


import psutil

TelemetryAttribute = namedtuple('TelemetryAttribute', ['name', 'description', 'formatter'])


class TelemetryInformation:
    start: float  # start of data collection for this telemetry frame
    end: float  # end of data collection for this telemetry frame
    enddate: datetime.datetime
    querytimes: List[float]
    outbufferlength: int
    messagessent: int
    messagesreceived: int
    oldestbufferedmessageage: float
    bytessent: int
    bytesreceived: int
    processid: int
    meminfo: NamedTuple
    outstandingvariables: List[str]
    coro_wakes: Dict[str, int]
    outdatedqueries: Dict[str, float]
    autoqueryinhibited: bool = False
    cleartosend: bool = False
    socket_eof: bool = False
    lastmessage: Tuple[bytes, int]
    lastsendtime: float
    lastrecvtime: float
    asyncio_tasks: List[str]
    comm_duration: float = 0.0
    communicating: bool=True
    commstart: Optional[float] = None

    attributeinfo: Final[List[TelemetryAttribute]] = [
        TelemetryAttribute('enddate', 'Date of telemetry', str),
        TelemetryAttribute('start', 'Start of data collection', lambda x: f'{x:.3f} sec'),
        TelemetryAttribute('end', 'End of data collection', lambda x: f'{x:.3f} sec'),
        TelemetryAttribute('duration', 'Data collection duration', lambda x: f'{x:.3f} sec'),
        TelemetryAttribute('memoryusage', 'Memory usage', lambda x: f'{x:.4f} GB'),
        TelemetryAttribute('bytessent', 'Bytes sent to device', str),
        TelemetryAttribute('bytesreceived', 'Bytes received from device', str),
        TelemetryAttribute('datarate', 'Data rate', lambda x: f'{x[0]:.2f} (out), {x[1]:.2f} (in) bytes/sec'),
        TelemetryAttribute('messagessent', 'Messages sent to device', str),
        TelemetryAttribute('messagesreceived', 'Messages received from device', str),
        TelemetryAttribute('messagerate', 'Message rate', lambda x: f'{x[0]:.2f} (out), {x[1]:.2f} (in) messages/sec'),
        TelemetryAttribute('lastmessage', 'Last message sent', str),
        TelemetryAttribute('cleartosend', 'Clear to send', str),
        TelemetryAttribute('socket_eof', 'Socket is in EOF state', str),
        TelemetryAttribute('autoqueryinhibited', 'Autoquery inhibited', str),
        TelemetryAttribute('outstandingvariables', 'Outstanding variables', lambda x: ', '.join(x)),
        TelemetryAttribute('outbufferlength', 'Output buffer length', str),
        TelemetryAttribute('oldestbufferedmessageage', 'Age of the oldest outgoing message', lambda x: f'{x} sec'),
        TelemetryAttribute(
            'coro_wakes', 'Coroutine wakes', lambda x: '\n' + '\n'.join([f'    {name}: {x[name]}' for name in sorted(x)])),
        TelemetryAttribute(
            'outdatedqueries', 'Outdated queries', lambda x: '\n'+'\n'.join([f'    {name}: {x[name]}' for name in sorted(x)])),
        TelemetryAttribute(
            'asyncio_tasks', 'Number of asyncio tasks',
            lambda x: '\n'+'\n'.join([f'    {name}: {x.count(name)}' for name in sorted(set(x))])),
        TelemetryAttribute(
            'comm_duration', 'Time spent with communication', lambda x: f'{x:.2f} sec'),
    ]


    def __init__(self, iscommunicating: bool=False):
        self.start = time.monotonic()
        self.querytimes = []
        self.bytessent = 0
        self.bytesreceived = 0
        self.outbufferlength = 0
        self.messagessent = 0
        self.messagesreceived = 0
        self.outstandingvariables = None
        self.processid = os.getpid()
        self.end = None
        self.oldestbufferedmessageage = 0.0
        self.outdatedqueries = {}
        self.coro_wakes = {}
        self.lastmessage = None
        self.commstart = time.monotonic() if iscommunicating else None
        self.communicating = iscommunicating

    def finish(self):
        self.end = time.monotonic()
        self.enddate = datetime.datetime.now()
        proc = psutil.Process(self.processid)
        self.meminfo = proc.memory_full_info()

    def __str__(self) -> str:
        return 'Telemetry information\n' + textwrap.indent('\n'.join(
            [f'{label}: {formatter(getattr(self, name))}' for name, label, formatter in self.attributeinfo]
        ), '    ')

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def memoryusage(self) -> float:
        """Memory usage in GBytes"""

        # meminfo members are in bytes -> divide three times by 1024 to get KB -> MB -> GB
        return (self.meminfo.uss + self.meminfo.pss)/2**30

    @property
    def datarate(self) -> Tuple[float, float]:
        return (self.bytessent/self.duration, self.bytesreceived/self.duration)

    @property
    def messagerate(self) -> Tuple[float, float]:
        return (self.messagessent/self.duration, self.messagesreceived/self.duration)

    def setCommunicating(self, commstatus: bool):
        if commstatus:
            self.commstart = time.monotonic()
        else:
            # self.commstart should not be None
            if self.commstart is None:
                self.commstart = self.start
            self.comm_duration += (time.monotonic() - self.commstart)
            self.commstart = None