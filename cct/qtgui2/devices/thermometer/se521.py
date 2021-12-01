import math
from typing import Any

from PyQt5 import QtWidgets

from .se521_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.devices.thermometer.se521 import SE521


class SE521Window(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicenames = ['SE521']
    _name_lineedits = {'t1name': 't1NameLineEdit', 't2name': 't2NameLineEdit', 't3name': 't3NameLineEdit',
                       't4name': 't4NameLineEdit', 't1-t2name': 't1minust2NameLineEdit'}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        for variable in self.device().keys():
            self.onVariableChanged(variable, self.device()[variable], None)
        self.backlightPushButton.clicked.connect(self.toggleBacklight)
        self.switchUnitsPushButton.clicked.connect(self.celsiusorfahrenheit)
        for widgetname in self._name_lineedits.values():
            widget: QtWidgets.QLineEdit = getattr(self, widgetname)
            widget.editingFinished.connect(self.onNameEdited)

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if name == 'battery_level':
            self.batteryLevelLabel.setText(f'{newvalue}/3')
        elif name == 'isrecallmode':
            self.recallModeLabel.setText(f'{"yes" if newvalue else "no"}')
        elif name in ['isalarm', 'islowalarm', 'ishighalarm']:
            try:
                if self.device()['islowalarm'] and self.device()['isalarm']:
                    self.alarmStateLabel.setText(f'Low temperature!')
                elif self.device()['ishighalarm'] and self.device()['isalarm']:
                    self.alarmStateLabel.setText(f'High temperature!')
                else:
                    self.alarmStateLabel.setText('Unknown alarm' if self.device()['isalarm'] else 'None')
            except self.device().DeviceError:
                if self.device().isInitializing():
                    # can happen when not all variables have been queried yet
                    pass
                else:
                    raise
        elif name == 'isrecording':
            self.recordingLabel.setText('yes' if newvalue else 'no')
        elif name == 'ismemoryfull':
            self.memoryFullLabel.setText('yes' if newvalue else 'no')
        elif name == 'isholdmode':
            self.holdModeLabel.setText('yes' if newvalue else 'no')
        elif name == 'isbluetoothenabled':
            self.bluetoothLabel.setText('yes' if newvalue else 'no')
        elif name in ['ismaxmode', 'ismaxminmode', 'isminmode', 'isavgmode', 'ismaxminavgflashing']:
            try:
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
            except self.device().DeviceError:
                if self.device().isInitializing():
                    # can happen when not all variables have been queried yet
                    pass
                else:
                    raise
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
        elif name in ['t1name', 't2name', 't3name', 't4name', 't1-t2name']:
            widget: QtWidgets.QLineEdit = {
                't1name': self.t1NameLineEdit,
                't2name': self.t2NameLineEdit,
                't3name': self.t3NameLineEdit,
                't4name': self.t4NameLineEdit,
                't1-t2name': self.t1minust2NameLineEdit}[name]
            widget.blockSignals(True)
            try:
                widget.setText(newvalue)
            finally:
                widget.blockSignals(False)

    def device(self) -> SE521:
        return self.instrument.devicemanager['se521']

    def toggleBacklight(self):
        self.device().toggleBacklight()

    def celsiusorfahrenheit(self):
        self.device().setDisplayUnits()

    def onNameEdited(self):
        for name, widgetname in self._name_lineedits.items():
            if self.sender().objectName() == widgetname:
                self.device().setChannelName(name.replace('name', ''), self.sender().text())
