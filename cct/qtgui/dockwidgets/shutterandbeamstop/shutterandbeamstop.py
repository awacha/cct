from PyQt5 import QtWidgets

from .shutterandbeamstop_ui import Ui_DockWidget
from ...core.mixins import ToolWindow
from ....core.devices.motor import Motor, TMCMCard
from ....core.devices.xray_source import GeniX
from ....core.instrument.instrument import Instrument
from ....core.instrument.privileges import PRIV_BEAMSTOP, PRIV_SHUTTER, PrivilegeLevel
from ....core.services.accounting import Accounting


class ShutterAndBeamstop(QtWidgets.QDockWidget, Ui_DockWidget, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QDockWidget.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo)
        self._genixconnections=[]
        self._bsxconnections=[]
        self._bsyconnections=[]
        self._bsxcontrollerconnections=[]
        self._bsycontrollerconnections=[]
        self.setupUi(self)

    def setupUi(self, DockWidget):
        Ui_DockWidget.setupUi(self, self)
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        self.setBSControlsEnabled()
        self.setShutterControlsEnabled()

    def onBeamStopMotorMovement(self, motor:Motor, newposition:float):
        pass

    def onBeamStopMotorControllerIdle(self, controller:TMCMCard, variable, newvalue):
        pass

    def onShutterChanged(self, genix:GeniX, variablename: str, newvalue: bool):
        if variablename == 'shutter':
            if newvalue:
                pass
            

    def onPrivLevelChanged(self, accountingservice:Accounting, privlevel:PrivilegeLevel):
        self.setShutterControlsEnabled()
        self.setBSControlsEnabled()

    def setBSControlsEnabled(self, idle=None):
        assert isinstance(self.credo, Instrument)
        privlevel = self.credo.services['accounting'].get_privilegelevel()
        bsOK=True
        for motname in ['Motor_BeamStop_X', 'Motor_BeamStop_Y']:
            try:
                motor = self.credo.get_device(motname)
            except KeyError:
                bsOK=False
                break
            assert isinstance(motor, Motor)
            if motor.controller.is_busy():
                bsOK=False
                break
        self.beamstopInPushButton.setEnabled(privlevel>=PRIV_BEAMSTOP and bsOK)
        self.beamstopOutPushButton.setEnabled(privlevel>=PRIV_BEAMSTOP and bsOK)

    def setShutterControlsEnabled(self):
        assert isinstance(self.credo, Instrument)
        privlevel = self.credo.services['accounting'].get_privilegelevel()
        try:
            genix = self.credo.get_device('genix')
            assert isinstance(genix, GeniX)
            genixOK=genix.can_open_shutter()
        except KeyError:
            genixOK=False
        self.openShutterPushButton.setEnabled(privlevel>=PRIV_SHUTTER and genixOK)
        self.closeShutterPushButton.setEnabled(privlevel>=PRIV_SHUTTER and genixOK)

    def onShutterOpen(self):
        pass

    def onShutterClose(self):
        pass

    def onBeamStopIn(self):
        pass

    def onBeamStopOut(self):
        pass

