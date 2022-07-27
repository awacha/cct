import datetime
import logging
from typing import Any

import h5py
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from .backend import HaakePhoenixBackend
from ...device.frontend import DeviceFrontend, DeviceType
from ....sensors.thermometer import Thermometer


class HaakePhoenix(DeviceFrontend):
    backendclass = HaakePhoenixBackend
    devicename = 'HaakePhoenix'
    devicetype = DeviceType.Thermostat
    vendor = 'Haake'
    temperatureChanged = Signal(float)
    startStop = Signal(bool)
    loglevel = logging.INFO

    def __init__(self, name: str, host: str, port: int, **kwargs):
        super().__init__(name, host, port, **kwargs)
        self.sensors = [Thermometer(f'temperature', self.name, 0, '°C'),
                        Thermometer(f'internal', self.name, 1, '°C'),
                        Thermometer(f'external', self.name, 2, '°C'),
                        ]

    def temperature(self) -> float:
        return self['temperature']

    def highlimit(self) -> float:
        return self['highlimit']

    def lowlimit(self) -> float:
        return self['lowlimit']

    def setpoint(self) -> float:
        return self['setpoint']

    def startCirculator(self):
        self.issueCommand('start')

    def stopCirculator(self):
        self.issueCommand('stop')

    def setSetpoint(self, setpoint: float):
        self.issueCommand('setpoint', setpoint)

    def setLowLimit(self, lowlimit: float):
        self.issueCommand('lowlimit', lowlimit)

    def setHighLimit(self, highlimit: float):
        self.issueCommand('highlimit', highlimit)

    def setDate(self, date: datetime.date):
        self.issueCommand('setdate', date)

    def setTime(self, time: datetime.time):
        self.issueCommand('settime', time)

    def isRunning(self) -> bool:
        return self['__status__'] == HaakePhoenixBackend.Status.Running

    def onVariableChanged(self, variablename: str, newvalue: Any, previousvalue: Any):
        super().onVariableChanged(variablename, newvalue, previousvalue)
        if variablename == '__status__':
            if newvalue == HaakePhoenixBackend.Status.Running:
                self.startStop.emit(True)
            elif newvalue == HaakePhoenixBackend.Status.Stopped:
                self.startStop.emit(False)
            else:
                pass
        elif variablename == 'temperature':
            self.temperatureChanged.emit(float(newvalue))
            self.sensors[0].update(float(newvalue))
        elif variablename == 'temperature_internal':
            self.sensors[1].update(float(newvalue))
        elif variablename == 'temperature_external':
            self.sensors[2].update(float(newvalue))

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        grp = super().toNeXus(grp)
        self.create_hdf5_dataset(grp, 'type', self['firmwareversion'])
        self.create_hdf5_dataset(grp, 'description', 'Haake Phoenix 2P circulating bath')
        sensorgrp = grp.create_group('temperature')
        sensorgrp.attrs['NX_class'] = 'NXsensor'
        self.create_hdf5_dataset(sensorgrp, 'model', 'Haake Phoenix')
        self.create_hdf5_dataset(sensorgrp, 'name', 'temperature')
        self.create_hdf5_dataset(sensorgrp, 'short_name', 'sample block temperature')
        self.create_hdf5_dataset(sensorgrp, 'measurement', 'temperature')
        self.create_hdf5_dataset(sensorgrp, 'run_control', False)
        self.create_hdf5_dataset(sensorgrp, 'value', self['temperature'], units='°C')
        return grp