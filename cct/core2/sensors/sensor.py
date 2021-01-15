from PyQt5 import QtCore
import math


class Sensor(QtCore.QObject):
    name: str
    sensortype: str
    quantityname: str
    devicename: str
    index: int
    valueChanged = QtCore.pyqtSignal(float)
    _value: float
    units: str

    def __init__(self, name: str, devicename: str, index: int, units: str):
        self._value = math.nan
        self.name = name
        self.devicename = devicename
        self.index = index
        self.units = units
        super().__init__()

    def value(self):
        return self._value

    def update(self, newvalue: float):
        self._value = newvalue
        self.valueChanged.emit(newvalue)
