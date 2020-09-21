import os
import time
from typing import List, NamedTuple, Dict, Tuple

import psutil


class TelemetryInformation:
    start: float  # start of data collection for this telemetry frame
    end: float  # end of data collection for this telemetry frame
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

    def __init__(self):
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

    def finish(self):
        self.end = time.monotonic()
        proc = psutil.Process(self.processid)
        self.meminfo = proc.memory_full_info()

    def __str__(self) -> str:
        return ('Telemetry information\n'
                f'   start time: {self.start}\n'
                f'   memory usage: {(self.meminfo.uss + self.meminfo.pss)/2**30:.4f} GB\n'
                f'   duration: {self.end - self.start} seconds\n'
                f'   bytes sent: {self.bytessent}\n'
                f'   bytes received: {self.bytesreceived}\n'
                f'   messages sent: {self.messagessent}\n'
                f'   messages received: {self.messagesreceived}\n'
                f'   clear to send: {self.cleartosend}\n'
                f'   last message: {self.lastmessage}\n'
                f'   socket EOF: {self.socket_eof}\n'
                f'   autoquery inhibited: {self.autoqueryinhibited}\n'
                f'   outstanding variables: {self.outstandingvariables}\n'
                f'   output buffer length: {self.outbufferlength}\n'
                f'   age of the oldest hardware-bound message: {self.oldestbufferedmessageage} seconds\n'
                f'   coroutine wakes:\n' +
                '\n'.join([f'      {key}: {value}' for key, value in self.coro_wakes.items()]) + '\n' +
                f'   outdated queries:\n' +
                '\n'.join([f'      {key}: {value}' for key, value in self.outdatedqueries.items()]) + '\n' +
                f'   last send time - last recv time: {(self.lastsendtime - self.lastrecvtime) if (self.lastsendtime is not None) and (self.lastrecvtime is not None) else None}'
                )

    def duration(self) -> float:
        return self.end - self.start
