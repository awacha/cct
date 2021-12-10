from math import inf
from multiprocessing import Queue
from typing import Tuple, List, Sequence, Any

from ...device.backend import DeviceBackend, VariableType


class TPG201Backend(DeviceBackend):
    class Status(DeviceBackend.Status):
        NoVacuum = 'No vacuum'
        MediumVacuum = 'Medium vacuum'
        VacuumOK = 'Vacuum OK'

    varinfo = [
        # version of the firmware running in the TMCM controller. Query only once, at the beginning.
        DeviceBackend.VariableInfo(name='pressure', dependsfrom=[], urgent=False, timeout=0.5, vartype=VariableType.FLOAT),
        DeviceBackend.VariableInfo(name='version', dependsfrom=[], urgent=False, timeout=inf, vartype=VariableType.STR),
        DeviceBackend.VariableInfo(name='units', dependsfrom=[], urgent=False, timeout=inf, vartype=VariableType.STR),
    ]

    def __init__(self, inqueue: Queue, outqueue: Queue, host: str, port: int):
        super().__init__(inqueue, outqueue, host, port)

    def issueCommand(self, name: str, args: Sequence[Any]):
        self.commandError(name, 'No commands supported by this device')

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        msgs = message.split(b'\r')
        return msgs[:-1], msgs[-1]

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        # message should start with b'001'
        if message[:3] != b'001':
            raise ValueError(f'Invalid message: does not start with "001" ({message})')
        # checksum validation
        if (sum(message[:-1]) % 64 + 64) != message[-1]:
            raise ValueError(f'Message checksum error ${message}')
        if message[3:4] == b'M':  # measurement
            pressure = float(message[4:8]) * 10 ** (-23 + float(message[8:10]))
            self.updateVariable('pressure', pressure)
            if pressure >= 1:
                self.updateVariable('__status__', self.Status.NoVacuum)
            elif pressure >= 0.1:
                self.updateVariable('__status__', self.Status.MediumVacuum)
            else:
                self.updateVariable('__status__', self.Status.VacuumOK)
            self.updateVariable('__auxstatus__', f'{pressure:.4f} mbar')
        elif message[3:4] == b'T':
            self.updateVariable('version', message[4:10].decode('ascii'))
        elif message[3:4] == b'U':
            self.updateVariable('units', message[4:10].decode('ascii'))
        else:
            self.error(f'Unknown message: {message}')

    def _query(self, variablename: str):
        if variablename == 'pressure':
            self.enqueueHardwareMessage(b'001M^\r')
        elif variablename == 'version':
            self.enqueueHardwareMessage(b'001Te\r')
        elif variablename == 'units':
            self.enqueueHardwareMessage(b'001Uf\r')
