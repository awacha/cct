"""Logger for device variables in a NeXus-conforming HDF5 file"""
import datetime
import time
from multiprocessing.synchronize import Lock
from typing import Dict, Any, Optional, List

import h5py
from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot

from ..devices.device.frontend import DeviceFrontend


class NXLogger(QtCore.QObject):
    """Facility to create and update NXlog groups from device parameters while an exposure is running."""
    filename: str
    lock: Lock
    path: str
    device: DeviceFrontend
    attrs: Dict[str, Any]
    starttime: Optional[float] = None
    writepointers: Dict[str, int]
    increment: int = 10
    notloggable: List[str]

    def __int__(self, filename: str, path: str, device: DeviceFrontend, lock: Lock, increment: int = 10, notloggable: Optional[List[str]] = None):
        """

        :param filename: the name of the HDF5 file to write the log to
        :type filename: str
        :param path: absolute HDF5 path in the file, e.g. 'entry1/instrument/source/logs'
        :type path: str
        :param device: the device object of which the variables are to be logged
        :type device: DeviceFrontend instance
        :param lock: a multiprocessing-style Lock associated with the HDF5 file
        :type lock: multiprocessing.Lock instance
        :param increment: when out of space in the list, reserve this many new places
        :type increment: int
        :param notloggable: list of variable names which should not be logged
        :type notloggable: list of str
        """
        super().__init__()
        self.filename = filename
        self.path = path
        self.device = device
        self.lock = lock
        self.starttime = None
        self.writepointers = {}
        self.notloggable = notloggable if notloggable is not None else []
        self.increment = increment

    def isRunning(self) -> bool:
        """Check if this logger is already running."""
        return self.starttime is not None

    def start(self):
        if self.isRunning():
            raise RuntimeError('Already running')
        self.starttime = time.monotonic()
        starttimestamp=datetime.datetime.now().astimezone().isoformat()
        self.device.variableChanged.connect(self.onVariableChanged)
        with self.lock:
            with h5py.File(self.filename, 'a') as h5:
                h5.swmr_mode = True
                for variablename, value in self.device:
                    if variablename in self.notloggable:
                        continue
                    grp = h5.require_group(self.path+'/'+variablename)
                    ds = grp.create_dataset('time', shape=(1,), maxshape=(None,), data=time.monotonic()-self.starttime).attrs['units'] = 's'
                    ds.attrs['start'] = starttimestamp
                    grp.create_dataset('value', shape=(1,), maxshape=(None,), data=value)
                    self.writepointers[variablename] = 1  # the next index to write the data

    def stop(self):
        if not self.isRunning():
            raise RuntimeError('Not running')
        self.device.variableChanged.disconnect(self.onVariableChanged)
        # write the current values
        for variablename, value in self.device:
            self.appendData(variablename, value)
        # truncate the arrays
        with self.lock:
            with h5py.File(self.filename, 'a') as h5:
                h5.swmr_mode = True
                for grpname in h5[self.path]:
                    grp = h5[self.path][grpname]
                    grp['time'].resize(self.writepointers[grpname])
                    grp['value'].resize(self.writepointers[grpname])
        self.starttime = None

    @Slot(str, object, object, name='onVariableChanged')
    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        self.appendData(variablename, newvalue)

    def appendData(self, variablename: str, value: Any):
        if variablename in self.notloggable:
            return
        with self.lock:
            with h5py.File(self.filename, 'a') as h5:
                h5.swmr_mode = True
                grp = h5[self.path+'/'+variablename]
                if grp['time'].size == self.writepointers[variablename]:
                    # not enough space left in the array
                    grp['time'].resize(grp['time'].size + self.increment)
                    grp['value'].resize(grp['value'].size + self.increment)
                grp['time'][self.writepointers[variablename]] = time.monotonic() - self.starttime
                grp['value'][self.writepointers[variablename]] = value
                self.writepointers[variablename] += 1
