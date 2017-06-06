from typing import Union

from PyQt5 import QtWidgets

from .vacuum_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.devices import Device, Motor
from ....core.devices.vacuumgauge import TPG201


class VacuumGauge(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['tpg201']

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo=credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        dev = self.credo.get_device('tpg201')
        assert isinstance(dev, TPG201)
        for var in dev.all_variables + ['_status']:
            self.onDeviceVariableChange(dev, var, dev.get_variable(var))

    def onDeviceVariableChange(self, device: Union[Device, Motor], variablename: str, newvalue):
        assert isinstance(device, TPG201)
        if variablename == 'pressure':
            self.vacuumLcdNumber.display(newvalue)
        elif variablename == '_status':
            self.statusLabel.setText(newvalue)
        elif variablename == 'version':
            self.versionLabel.setText(newvalue)
        else:
            pass
