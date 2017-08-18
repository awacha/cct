import datetime
from typing import Union, Optional

from PyQt5 import QtWidgets, QtGui

from .circulator_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.devices import Device, Motor
from ....core.devices.circulator import HaakePhoenix


class TemperatureController(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['haakephoenix']

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        dev = self.credo.get_device('haakephoenix')
        assert isinstance(dev, HaakePhoenix)
        for var in dev.all_variables + ['_status']:
            self.onDeviceVariableChange(dev, var, dev.get_variable(var))
        self.updateHighLimitPushButton.clicked.connect(self.onUpdateHighLimit)
        self.updateLowLimitPushButton.clicked.connect(self.onUpdateLowLimit)
        self.updateSetPointPushButton.clicked.connect(self.onUpdateSetpoint)
        self.startStopPushButton.clicked.connect(self.onStartStop)
        self.updateRTCPushButton.clicked.connect(self.onUpdateRTC)
        self.lowLimitDoubleSpinBox.editingFinished.connect(self.onLowLimitEditingFinished)
        self.highLimitDoubleSpinBox.editingFinished.connect(self.onHighLimitEditingFinished)
        self.setPointDoubleSpinBox.editingFinished.connect(self.onSetPointEditingFinished)

    def onLowLimitEditingFinished(self):
        if self.lowLimitDoubleSpinBox.hasFocus():
            self.onUpdateLowLimit()

    def onHighLimitEditingFinished(self):
        if self.highLimitDoubleSpinBox.hasFocus():
            self.onUpdateHighLimit()

    def onSetPointEditingFinished(self):
        if self.setPointDoubleSpinBox.hasFocus():
            self.onUpdateSetpoint()

    def onUpdateRTC(self):
        dev = self.credo.get_device('haakephoenix')
        assert isinstance(dev, HaakePhoenix)
        dev.set_variable('date', datetime.date.today())
        dev.set_variable('time', datetime.datetime.now().time())

    def onUpdateLowLimit(self):
        dev = self.credo.get_device('haakephoenix')
        assert isinstance(dev, HaakePhoenix)
        dev.set_variable('lowlimit', self.lowLimitDoubleSpinBox.value())

    def onUpdateHighLimit(self):
        dev = self.credo.get_device('haakephoenix')
        assert isinstance(dev, HaakePhoenix)
        dev.set_variable('highlimit', self.highLimitDoubleSpinBox.value())

    def onUpdateSetpoint(self):
        dev = self.credo.get_device('haakephoenix')
        assert isinstance(dev, HaakePhoenix)
        dev.set_variable('setpoint', self.setPointDoubleSpinBox.value())

    def onStartStop(self):
        dev = self.credo.get_device('haakephoenix')
        assert isinstance(dev, HaakePhoenix)
        if self.startStopPushButton.text() == 'Start':
            dev.execute_command('start')
            self.startStopPushButton.setEnabled(False)
        elif self.startStopPushButton.text() == 'Stop':
            dev.execute_command('stop')
            self.startStopPushButton.setEnabled(False)
        else:
            # should not happen.
            assert False

    def setFlagBackground(self, flag: QtWidgets.QLabel, state: bool, label: Optional[str] = None):
        palette = flag.palette()
        assert isinstance(palette, QtGui.QPalette)
        if state is None:
            palette.setColor(QtGui.QPalette.Window, QtGui.QColor('gray'))
        elif state:
            palette.setColor(QtGui.QPalette.Window, QtGui.QColor('green'))
        else:
            palette.setColor(QtGui.QPalette.Window, QtGui.QColor('red'))
        flag.setPalette(palette)
        flag.setAutoFillBackground(True)
        if label is not None:
            flag.setText(label)

    def onDeviceVariableChange(self, device: Union[Device, Motor], variablename: str, newvalue):
        if variablename == 'firmwareversion':
            self.firmwareVersionLabel.setText(newvalue)
        elif variablename == 'fuzzycontrol':
            self.setFlagBackground(self.fuzzyControlStatusFlag, newvalue, newvalue)
        elif variablename == 'fuzzystatus':
            self.setFlagBackground(self.fuzzyStatusStatusFlag, newvalue)
        elif variablename == 'temperature':
            self.temperatureLcdNumber.display(newvalue)
        elif variablename == 'setpoint':
            self.setpointLcdNumber.display(newvalue)
            self.setPointDoubleSpinBox.setValue(newvalue)
        elif variablename == 'highlimit':
            self.highLimitLcdNumber.display(newvalue)
            self.highLimitDoubleSpinBox.setValue(newvalue)
        elif variablename == 'lowlimit':
            self.lowLimitLcdNumber.display(newvalue)
            self.lowLimitDoubleSpinBox.setValue(newvalue)
        elif variablename == 'diffcontrol_on':
            self.setFlagBackground(self.diffControlStatusFlag, newvalue)
        elif variablename == 'autostart':
            self.setFlagBackground(self.autostartStatusFlag, newvalue)
        elif variablename == 'fuzzyid':
            pass
        elif variablename == 'beep':
            self.setFlagBackground(self.beepStatusFlag, newvalue)
        elif variablename == 'time':
            self.rtcTimeEdit.setTime(newvalue)
        elif variablename == 'date':
            self.rtcDateEdit.setDate(newvalue)
        elif variablename == 'cooling_on':
            self.setFlagBackground(self.coolingOnStatusFlag, newvalue)
        elif variablename == 'pump_power':
            self.pumpSpeedLcdNumber.display(newvalue)
        elif variablename == 'external_pt100_error':
            self.setFlagBackground(self.externalPt100ErrorFlag, not newvalue)
        elif variablename == 'internal_pt100_error':
            self.setFlagBackground(self.internalPt100ErrorFlag, not newvalue)
        elif variablename == 'liquid_level_low_error':
            self.setFlagBackground(self.liquidLevelErrorFlag, not newvalue)
        elif variablename == 'cooling_error':
            self.setFlagBackground(self.coolingSystemErrorFlag, not newvalue)
        elif variablename == 'external_alarm_error':
            self.setFlagBackground(self.externalAlarmErrorFlag, not newvalue)
        elif variablename == 'pump_overload_error':
            self.setFlagBackground(self.pumpErrorFlag, not newvalue)
        elif variablename == 'liquid_level_alarm_error':
            self.setFlagBackground(self.liquidLevelAlarmErrorFlag, not newvalue)
        elif variablename == 'overtemperature_error':
            self.setFlagBackground(self.overtemperatureErrorFlag, not newvalue)
        elif variablename == 'main_relay_missing_error':
            self.setFlagBackground(self.mainRelayErrorFlag, not newvalue)
        elif variablename == '_status':
            self.statusLabel.setText(newvalue)
            if newvalue == 'running':
                self.startStopPushButton.setText('Stop')
                self.startStopPushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
                self.startStopPushButton.setEnabled(True)
            elif newvalue == 'stopped':
                self.startStopPushButton.setText('Start')
                self.startStopPushButton.setIcon(QtGui.QIcon.fromTheme('system-run'))
                self.startStopPushButton.setEnabled(True)
        elif variablename == 'control_on':
            self.setFlagBackground(self.temperatureControlFlag, newvalue)
        elif variablename == 'control_external':
            self.setFlagBackground(self.externalControlStatusFlag, newvalue)
        else:
            print('Unknown variable: {} = {}'.format(variablename, newvalue))
