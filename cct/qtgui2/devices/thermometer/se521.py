import math
from typing import Any

from PyQt5 import QtWidgets

from .se521_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.devices.thermometer.se521 import SE521


class SE521Window(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicenames = ['SE521']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        for variable in self.device().keys():
            self.onVariableChanged(variable, self.device()[variable], None)
        self.backlightPushButton.clicked.connect(self.toggleBacklight)
        self.switchUnitsPushButton.clicked.connect(self.celsiusorfahrenheit)

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if name == 'battery_level':
            self.batteryLevelLabel.setText(f'{newvalue}/3')
        elif name == 'isrecallmode':
            self.recallModeLabel.setText(f'{"yes" if newvalue else "no"}')
        elif name in ['isalarm', 'islowalarm', 'ishighalarm']:
            if self.device()['islowalarm'] and self.device['isalarm']:
                self.alarmStateLabel.setText(f'Low temperature!')
            elif self.device()['ishighalarm'] and self.device['isalarm']:
                self.alarmStateLabel.setText(f'High temperature!')
            else:
                self.alarmStateLabel.setText('Unknown alarm' if self.device()['isalarm'] else 'None')
        elif name == 'isrecording':
            self.recordingLabel.setText('yes' if newvalue else 'no')
        elif name == 'ismemoryfull':
            self.memoryFullLabel.setText('yes' if newvalue else 'no')
        elif name == 'isholdmode':
            self.holdModeLabel.setText('yes' if newvalue else 'no')
        elif name == 'isbluetoothenabled':
            self.bluetoothLabel.setText('yes' if newvalue else 'no')
        elif name in ['ismaxmode', 'ismaxminmode', 'isminmode', 'isavgmode', 'ismaxminavgflashing']:
            if self.device()['ismaxmode']:
                self.displayModeLabel.setText('Max')
            elif self.device()['isminmode']:
                self.displayModeLabel.setText('Min')
            elif self.device()['isavgmode']:
                self.displayModeLabel.setText('Avg')
            elif self.device()['ismaxminavgflashing']:
                self.displayModeLabel.setText('Max/Min/Avg')
            else:
                self.displayModeLabel.setText('Current')
        elif name == 'thermistortype':
            self.thermistorTypeLabel.setText(newvalue)
        elif name in ['t1', 't2', 't3', 't4', 't1-t2']:
            if name == 't1-t2':
                labelwidget = self.t1minust2Label
            else:
                labelwidget = getattr(self, name + 'Label')
            assert isinstance(labelwidget, QtWidgets.QLabel)
            if math.isnan(newvalue):
                labelwidget.setText('Unplugged')
            elif math.isinf(newvalue):
                labelwidget.setText('Out of range')
            else:
                labelwidget.setText(f'{newvalue:.1f}°C')
        elif name == 'firmwareversion':
            self.deviceTypeLabel.setText(newvalue)

    def device(self) -> SE521:
        return self.instrument.devicemanager['SE521']

    def toggleBacklight(self):
        self.device().toggleBacklight()

    def celsiusorfahrenheit(self):
        self.device().setDisplayUnits()
