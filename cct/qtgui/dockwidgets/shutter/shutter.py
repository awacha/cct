from typing import Union

from PyQt5 import QtWidgets

from .shutter_ui import Ui_DockWidget
from ...core.mixins import ToolWindow
from ....core.devices import GeniX, Device, Motor
from ....core.instrument.privileges import PRIV_SHUTTER
from ....core.utils.inhibitor import Inhibitor


class ShutterDockWidget(QtWidgets.QDockWidget, Ui_DockWidget, ToolWindow):
    required_privilege = PRIV_SHUTTER
    required_devices = ['genix']
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QDockWidget.__init__(self, *args, **kwargs)
        self._updating_ui = Inhibitor()
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, DockWidget):
        Ui_DockWidget.setupUi(self,DockWidget)
        self.shutterToolButton.toggled.connect(self.onShutter)

    def onShutter(self):
        if self._updating_ui:
            return
        genix=self.credo.get_device('genix')
        assert isinstance(genix, GeniX)
        genix.shutter(self.shutterToolButton.isChecked())

    def onDeviceVariableChange(self, device: Union[Device, Motor], variablename: str, newvalue):
        assert device.name=='genix'
        if variablename == 'shutter':
            with self._updating_ui:
                self.shutterToolButton.setChecked(newvalue)

        elif variablename == 'interlock':
            with self._updating_ui:
                self.shutterToolButton.setEnabled(newvalue)
        return False