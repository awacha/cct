"""Logger for device variables in a NeXus-conforming HDF5 file"""
import datetime
import time
from multiprocessing.synchronize import Lock
from typing import Dict, Any, Optional, List

import numpy as np
import h5py
from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot

from ..devices.device.frontend import DeviceFrontend
from ..devices.device.variable import VariableType


class NXLogger(QtCore.QObject):
    """Facility to create and update NXlog groups from device parameters while an exposure is running."""
    group: h5py.Group
    device: DeviceFrontend
    attrs: Dict[str, Any]
    starttime: Optional[float] = None
    writepointers: Dict[str, int]
    increment: int = 10
    notloggable: List[str]

    def __int__(self, parentgroup: h5py.Group, name: str, device: DeviceFrontend, increment: int = 10, notloggable: Optional[List[str]] = None):
        """

        :param parentgroup: the parent HDF5 group into which the NXlog group is to be written
        :type parentgroup: h5py.Group
        :param name: name of the group to create
        :type name: str
        :param device: the device object of which the variables are to be logged
        :type device: DeviceFrontend instance
        :param increment: when out of space in the list, reserve this many new places
        :type increment: int
        :param notloggable: list of variable names which should not be logged
        :type notloggable: list of str
        """
        super().__init__()
        self.group = parentgroup.create_group(name)
        self.group.attrs['NX_class'] = 'NXlog'
        self.device = device
        self.starttime = None
        self.writepointers = {}
        self.notloggable = notloggable if notloggable is not None else []
        self.increment = increment
        self.starttime = time.monotonic()
        starttime = datetime.datetime.now().astimezone()
        for var in self.device.variables():
            if var.name in self.notloggable:
                continue
            if var.vartype is VariableType.INT:
                dtype = int
            elif var.vartype is VariableType.FLOAT:
                dtype = float
            elif var.vartype is VariableType.STR:
                dtype = h5py.string_dtype()
            elif var.vartype is VariableType.BYTES:
                dtype = h5py.opaque_dtype(np.bytes)
            elif var.vartype is VariableType.BOOL:
                dtype = bool
            elif var.vartype is VariableType.DATETIME:
                dtype = h5py.string_dtype()
            elif var.vartype is VariableType.DATE:
                dtype = h5py.string_dtype()
            elif var.vartype is VariableType.TIME:
                dtype = h5py.string_dtype()
            else:
                continue
            grp = self.group.create_group(var.name)
            dstime = grp.create_dataset('time', shape=(1,), maxshape=(None,), dtype=float)
            dstime.attrs['start'] = starttime.isoformat()
            grp.create_dataset('value', shape=(1,), maxshape=(None,), dtype=dtype)
            self.writepointers[var.name] = 0
            self.appendData(var.name, var.value)

    def finalize(self):
        for varname in self.group:
            vargroup: h5py.Group = self.group[varname]
            value = self.device[varname]
            vargroup




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
        if variablename not in self.group:
            return
        if self.group[variablename]['time'].size <= self.writepointers[variablename]:
            # make space
            self.group[variablename]['time'].resize((self.group[variablename]['time'].size + self.increment,))
            self.group[variablename]['value'].resize((self.group[variablename]['value'].size + self.increment,))
        self.group[variablename]['time'][self.writepointers[variablename]] = time.monotonic() - self.starttime
        if h5py.check_dtype()
        self.group[variablename]['value'][self.writepointers[variablename]] = value
        self.writepointers[variablename] += 1
