import logging
from typing import Any

import h5py
import numpy as np
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from .backend import SE521Backend
from ...device.frontend import DeviceFrontend, DeviceType
from ....sensors.thermometer import Thermometer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SE521(DeviceFrontend):
    backendclass = SE521Backend
    devicename = 'SE521'
    vendor = 'Thermosense'
    devicetype = DeviceType.Thermometer
    temperatureChanged = Signal(int, float)

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(name, host, port, **kwargs)
        self.sensors = [Thermometer(f't{i}', self.name, i-1, '°C') for i in range(1, 5)]

    def temperature(self, index: int) -> float:
        return self[f't{index}']

    def toggleBacklight(self):
        self.issueCommand('togglebacklight')

    def setDisplayUnits(self):
        self.issueCommand('changeunits')

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename in ['t1', 't2', 't3', 't4']:
            self.temperatureChanged.emit(int(variablename[1]), float(newvalue))
            self.sensors[int(variablename[1])-1].update(float(newvalue))
        elif variablename == 't1name':
            self.sensors[0].name = newvalue
        elif variablename == 't2name':
            self.sensors[1].name = newvalue
        elif variablename == 't3name':
            self.sensors[2].name = newvalue
        elif variablename == 't4name':
            self.sensors[3].name = newvalue

    def setChannelName(self, channel: str, newname: str):
        if channel not in ['t1', 't2', 't3', 't4', 't1-t2']:
            raise ValueError('Invalid channel name: can only be "t1", "t2", "t3", "t4" or "t1-t2".')
        self.issueCommand(f'set{channel}name', newname)

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        grp = super().toNeXus(grp)
        grp.attrs['NX_class'] = 'NXsensor'
        self.create_hdf5_dataset(grp, 'model', 'SE521')
        self.create_hdf5_dataset(grp, 'name', 'SE521 4-channel digital thermometer')
        self.create_hdf5_dataset(grp, 'short_name', 'Sample chamber temperature')
        self.create_hdf5_dataset(grp, 'measurement', 'temperature')
        self.create_hdf5_dataset(grp, 'type', self['thermistortype'])
        self.create_hdf5_dataset(grp, 'run_control', False)
        self.create_hdf5_dataset(grp, 'value', np.array([self['t1'], self['t2'], self['t3'], self['t4']]))
        return grp