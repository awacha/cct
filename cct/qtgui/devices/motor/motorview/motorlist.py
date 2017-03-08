from PyQt5 import QtCore

from .....core.devices.motor import Motor
from .....core.instrument.instrument import Instrument


class MotorModel(QtCore.QAbstractItemModel):
    def __init__(self, *args, **kwargs):
        self.credo = kwargs.pop('credo')
        assert isinstance(self.credo, Instrument)
        super().__init__(*args, **kwargs)
        self._motor_connections=[]
        for m in self.credo.motors:
            motor = self.credo.motors[m]
            self._motor_connections.append((motor, motor.connect('variable-change', self.onMotorVariableChange)))

    def cleanup(self):
        for motor, cid in self._motor_connections:
            motor.disconnect(cid)
        self._motor_connections = []

    def onMotorVariableChange(self, motor:Motor, variable:str, value):
        variables = ['softleft', 'softright', 'actualposition', 'actualspeed', 'leftswitchstatus', 'rightswitchstatus', 'load', 'errorflags']
        try:
            column = variables.index(variable)
        except IndexError:
            return False
        row=sorted(self.credo.motors.keys()).index(motor.name)
        self.dataChanged.emit(self.index(row,column), self.index(row,column))
        return False

    def columnCount(self, parent=None, *args, **kwargs):
        return 9

    def rowCount(self, parent=None, *args, **kwargs):
        assert isinstance(self.credo, Instrument)
        return len(self.credo.motors)

    def parent(self, index: QtCore.QModelIndex = None):
        return QtCore.QModelIndex()

    def index(self, row, column, parent=None, *args, **kwargs):
        return self.createIndex(row, column, None)

    def data(self, index: QtCore.QModelIndex, role=None):
        motorname = sorted(self.credo.motors.keys())[index.row()]
        motor = self.credo.motors[motorname]
        assert isinstance(motor, Motor)
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return motorname
            elif index.column() == 1:
                return '{:.4f}'.format(motor.get_variable('softleft'))
            elif index.column() == 2:
                return '{:.4f}'.format(motor.get_variable('softright'))
            elif index.column() == 3:
                return '<b>{:.4f}</b>'.format(motor.get_variable('actualposition'))
            elif index.column() == 4:
                return '{:.4f}'.format(motor.get_variable('actualspeed'))
            elif index.column() == 5:
                return ''
            elif index.column() == 6:
                return ''
            elif index.column() == 7:
                return str(motor.get_variable('load'))
            elif index.column() == 8:
                return motor.decode_error_flags()
            else:
                return None
        elif role == QtCore.Qt.CheckStateRole:
            if index.column() == 5:
                return [QtCore.Qt.Unchecked, QtCore.Qt.Checked][motor.get_variable('leftswitchstatus')]
            elif index.column() == 6:
                return [QtCore.Qt.Unchecked, QtCore.Qt.Checked][motor.get_variable('rightswitchstatus')]
            else:
                return None

    def flags(self, index:QtCore.Qt.QModelIndex):
        return QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def headerData(self, column, orientation, role=None):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return \
            ['Motor name', 'Left limit', 'Right limit', 'Position', 'Speed', 'Left switch', 'Right switch', 'Load',
             'Status flags'][column]
