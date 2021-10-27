import logging
from typing import Any

from PyQt5 import QtWidgets, QtGui, QtCore

from .genix_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.devices.xraysource.genix.frontend import GeniXBackend, GeniX
from ....core2.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GeniXTool(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    instrument: Instrument
    required_devicenames = ['genix']

    _var2widget = {
        "__status__": "statusLabel",
        "ht": "voltageLcdNumber",
        "current": "currentLcdNumber",
        "power": "powerLcdNumber",
        "tubetime": "uptimeLcdNumber",
        "tube_temperature": "temperatureLcdNumber",
        "shutter": "shutterStateFlag",
        "remote_mode": "remoteControlFlag",
        "xrays": "xraysOnFlag",
        "conditions_auto": "canRampUpFlag",
        "faults": "faultsFlag",
        "xray_light_fault": "xrayLightsFlag",
        "shutter_light_fault": "shutterLightsFlag",
        "sensor2_fault": "sensor2Flag",
        "tube_position_fault": "tubePositionFlag",
        "vacuum_fault": "opticsVacuumFlag",
        "waterflow_fault": "waterCoolingFlag",
        "safety_shutter_fault": "shutterMechanicsFlag",
        "temperature_fault": "tubeTemperatureFlag",
        "sensor1_fault": "sensor1Flag",
        "relay_interlock_fault": "interlockRelayFlag",
        "door_fault": "doorSensorFlag",
        "filament_fault": "filamentFlag",
        "tube_warmup_needed": "warmupFlag",
        "interlock": "interlockFlag",
        "overridden": "overriddenFlag",

    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        device = self.instrument.devicemanager['genix']
        for variable in self._var2widget:
            self.onVariableChanged(variable, device[variable], None)
        self.onVariableChanged('__status__', device['__status__'], None)
        self.onVariableChanged('__auxstatus__', device['__auxstatus__'], None)
        self.resetFaultsPushButton.clicked.connect(self.onResetFaultsClicked)
        self.xraysOnPushButton.toggled.connect(self.onXraysOnToggled)
        self.warmUpPushButton.toggled.connect(self.onWarmUpToggled)
        self.shutterPushButton.toggled.connect(self.onShutterToggled)
        self.powerOffPushButton.clicked.connect(self.onPowerOffClicked)
        self.standbyPushButton.clicked.connect(self.onStandbyClicked)
        self.fullPowerPushButton.clicked.connect(self.onFullPowerClicked)

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if name in self._var2widget:
            widget = getattr(self, self._var2widget[name])
            if isinstance(widget, QtWidgets.QLabel) and self._var2widget[name].endswith('Flag'):
                pal = widget.palette()
                if name in ['remote_mode', 'xrays', 'interlock']:
                    newvalue = not newvalue
                pal.setColor(QtGui.QPalette.Window, QtGui.QColor('red' if bool(newvalue) else 'lightgreen'))
                widget.setPalette(pal)
                widget.setAutoFillBackground(True)
            elif isinstance(widget, QtWidgets.QLCDNumber):
                widget.display(newvalue)
            elif isinstance(widget, QtWidgets.QLabel):
                widget.setText(newvalue)
        if name == 'faultstatus':
            self.resetFaultsPushButton.setEnabled(newvalue)
        if name == 'remote_mode' or name == 'interlock':
            self.shutterPushButton.setEnabled(self.genix()['remote_mode'] and self.genix()['interlock'])
        if name == '__status__':
            self.xraysOnPushButton.setEnabled(newvalue in [GeniXBackend.Status.off, GeniXBackend.Status.xraysoff])
            self.warmUpPushButton.setEnabled(newvalue in [GeniXBackend.Status.off, GeniXBackend.Status.warmup])
            self.powerOffPushButton.setEnabled(
                newvalue not in [GeniXBackend.Status.off, GeniXBackend.Status.warmup, GeniXBackend.Status.xraysoff])
            self.standbyPushButton.setEnabled(newvalue in [GeniXBackend.Status.full, GeniXBackend.Status.off])
            self.fullPowerPushButton.setEnabled(newvalue in [GeniXBackend.Status.standby])
            if newvalue == GeniXBackend.Status.warmup:
                self.warmUpPushButton.blockSignals(True)
                self.warmUpPushButton.setChecked(True)
                self.warmUpPushButton.blockSignals(False)
            elif prevvalue == GeniXBackend.Status.warmup:
                self.warmUpPushButton.blockSignals(True)
                self.warmUpPushButton.setChecked(False)
                self.warmUpPushButton.blockSignals(False)
        if name == 'xrays':
            self.xraysOnPushButton.blockSignals(True)
            self.xraysOnPushButton.setChecked(self.genix()['xrays'])
            self.xraysOnPushButton.blockSignals(False)
        if name == 'shutter':
            self.shutterPushButton.blockSignals(True)
            self.shutterPushButton.setChecked(self.genix()['shutter'])
            self.shutterPushButton.blockSignals(False)

    def onResetFaultsClicked(self):
        self.genix().resetFaults()

    def onXraysOnToggled(self, state: bool):
        if state:
            self.genix().xraysOn()
        else:
            self.genix().xraysOff()

    def onWarmUpToggled(self, state: bool):
        if state:
            self.genix().startWarmUp()
        else:
            self.genix().stopWarmUp()

    def onShutterToggled(self, state: bool):
        logger.debug(f'onShutterToggled({state})')
        self.genix().moveShutter(state)

    def onPowerOffClicked(self):
        self.genix().powerDown()

    def onStandbyClicked(self):
        self.genix().standby()

    def onFullPowerClicked(self):
        self.genix().rampup()

    def genix(self) -> GeniX:
        device = self.instrument.devicemanager['genix']
        assert isinstance(device, GeniX)
        return device

    def onCommandResult(self, name: str, success: str, message: str):
        if not success:
            QtWidgets.QMessageBox.critical(self, 'Error', message)
