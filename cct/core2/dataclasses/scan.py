import datetime
import itertools
import logging
from typing import Sequence, BinaryIO, Union, Optional, Tuple

import dateutil.parser
import numpy as np

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Scan:
    index: int = None
    command: str = ''
    date: datetime.datetime
    comment: str = ''
    countingtime: float
    _data: np.ndarray
    _nextpoint: int

    def __init__(self, motorname: str, counters: Sequence[str], maxcounts: int, index: int, date: datetime.datetime, comment: str, command: str, countingtime: float):
        dtype = np.dtype(list(
            zip(itertools.chain([motorname], counters),
                itertools.repeat('f4'))))
        self._data = np.zeros(maxcounts, dtype=dtype)
        self._nextpoint = 0
        self.index = index
        self.date = date
        self.command = command
        self.comment = comment
        self.countingtime = countingtime

    @property
    def columnnames(self):
        return self._data.dtype.names

    @property
    def motorname(self):
        return self._data.dtype.names[0]

    def __getitem__(self, item):
        return self._data[:self._nextpoint][item]

    def __setitem__(self, item, value):
        self._data[item] = value

    @classmethod
    def fromspecfile(cls, specfile: Union[str, BinaryIO], index: Optional[int] = None):
        if isinstance(specfile, str):
            with open(specfile, 'rb') as f:
                return cls.fromspecfile(f, index)
        for line in specfile:
            if line.startswith(b'#S') and ((index is None) or (line.split()[1].decode('utf-8') == str(index))):
                break
        else:
            raise ValueError(f'Could not find scan index {index} in file {specfile.name}')
        command = line.split(None, 2)[-1].decode('utf-8')
        index = int(line.split(None, 2)[1])
        startpos = []
        maxpoints = None
        scan = None
        comment = []
        for full_line in specfile:
            line = full_line.strip().decode('utf-8')
            if line.startswith('#D'):  # this is the date
                date = dateutil.parser.parse(line.split(None, 1)[1])
            elif line.startswith('#T'):  # this is the counting time
                countingtime, units = line.split(None, 2)[1:]
                if units != '(Seconds)':
                    raise ValueError(f'Unsupported time unit: {units}')
                countingtime = float(countingtime)
            elif line.startswith('#G') or line.startswith('#Q') or line.startswith('#U'):  # ignore these
                continue
            elif line.startswith('#P'):  # motor start positions
                startpos.extend([float(x) for x in line.split()[1:]])
            elif line.startswith('#N'):  # scan points
                maxpoints = int(line.split()[1])
            elif line.startswith('#C'):  # comment
                comment.append(line.split(None, 1)[1])
            elif line.startswith('#L'):  # column labels
                labels = line.split()[1:]
                if maxpoints is None:
                    raise ValueError('Maximum number of points not read.')
                scan = cls(labels[0], labels[1:], maxpoints, index, date, '\n'.join(comment), command, countingtime)
            elif line.startswith('#S'):  # this is another scan: break
                specfile.seek(-len(full_line), 1)
                break
            elif (not line.startswith('#')) and bool(line):  # scan data
                assert isinstance(scan, cls)
                scan.append(tuple([float(x) for x in line.split()]))
            else:
                continue
        return scan

    def append(self, readings: Tuple[float, ...]):
        if self._nextpoint < len(self._data):
            self._data[self._nextpoint] = readings
            self._nextpoint += 1
        else:
            raise ValueError('Cannot append to scan: already done.')

    def finished(self) -> bool:
        return self._nextpoint >= self._data.size

    def __len__(self) -> int:
        return self._nextpoint

    def maxpoints(self) -> int:
        return self._data.size

    def truncate(self):
        self._nextpoint = self._data.size
