import logging
from typing import Union

from PyQt5 import QtWidgets, QtGui

from .xraysource_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.devices import GeniX, Device, Motor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class XraySource(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['genix']

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        self._updating_ui=False
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        genix = self.credo.get_device('genix')
        assert isinstance(genix, GeniX)
        for var in genix.all_variables + ['_status']:
            self.onDeviceVariableChange(genix, var, genix.get_variable(var))
        self.fullPowerPushButton.clicked.connect(self.onFullPower)
        self.standbyPushButton.clicked.connect(self.onStandby)
        self.warmUpPushButton.toggled.connect(self.onWarmUp)
        self.resetFaultsPushButton.clicked.connect(self.onResetFaults)
        self.shutterPushButton.toggled.connect(self.onShutter)
        self.powerOffPushButton.clicked.connect(self.onPowerOff)
        self.xraysOnPushButton.toggled.connect(self.onXraysOn)

    def onFullPower(self):
        if self._updating_ui:
            return
        genix = self.credo.get_device('genix')
        assert isinstance(genix, GeniX)
        try:
            genix.set_power('full')
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, 'Error', 'Cannot power up X-ray tube: '+exc.args[0])

    def onStandby(self):
        if self._updating_ui:
            return
        genix = self.credo.get_device('genix')
        assert isinstance(genix, GeniX)
        try:
            genix.set_power('low')
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, 'Error', 'Cannot set X-ray tube to standby mode: '+exc.args[0])

    def onWarmUp(self):
        if self._updating_ui:
            return
        genix = self.credo.get_device('genix')
        assert isinstance(genix, GeniX)
        if self.warmUpPushButton.isChecked():
            try:
                genix.start_warmup()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, 'Error', 'Cannot start warm-up procedure: '+exc.args[0])
        else:
            try:
                genix.stop_warmup()
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, 'Error', 'Cannot stop warm-up procedure: '+exc.args[0])


    def onPowerOff(self):
        if self._updating_ui:
            return
        genix = self.credo.get_device('genix')
        assert isinstance(genix, GeniX)
        try:
            genix.set_power('off')
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, 'Error', 'Cannot power off X-ray tube: '+exc.args[0])

    def onShutter(self):
        if self._updating_ui:
            return
        genix = self.credo.get_device('genix')
        assert isinstance(genix, GeniX)
        genix.shutter(self.shutterPushButton.isChecked())

    def onXraysOn(self):
        if self._updating_ui:
            return
        genix = self.credo.get_device('genix')
        assert isinstance(genix, GeniX)
        genix.set_xrays(self.xraysOnPushButton.isChecked())

    def onResetFaults(self):
        if self._updating_ui:
            return
        genix = self.credo.get_device('genix')
        assert isinstance(genix, GeniX)
        genix.reset_faults()

    def setFlagBackground(self, flag:QtWidgets.QLabel, state:bool):
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

    def onDeviceVariableChange(self, device: Union[Device, Motor], variablename: str, newvalue):
        self._updating_ui = True
        try:
            assert isinstance(device, GeniX)
            if variablename == 'ht':
                self.voltageLcdNumber.display(newvalue)
            elif variablename == 'current':
                self.currentLcdNumber.display(newvalue)
            elif variablename == 'power':
                self.powerLcdNumber.display(newvalue)
            elif variablename == 'tubetime':
                self.uptimeLcdNumber.display(newvalue)
            elif variablename == 'shutter':
                self.setFlagBackground(self.shutterStateFlag, not newvalue)
                self.shutterStateFlag.setText(['Shutter closed', 'Shutter open'][newvalue])
                self.shutterPushButton.setChecked(newvalue)
            elif variablename == 'remote_mode':
                self.setFlagBackground(self.remoteControlFlag, newvalue)
            elif variablename == 'conditions_auto':
                self.setFlagBackground(self.canRampUpFlag, newvalue)
            elif variablename == 'xrays':
                self.setFlagBackground(self.xraysOnFlag, newvalue)
                self.xraysOnFlag.setText(['X-rays off', 'X-rays on'][newvalue])
                self.xraysOnPushButton.setChecked(newvalue)
            elif variablename == 'faults':
                self.setFlagBackground(self.faultsFlag, not newvalue)
                self.resetFaultsPushButton.setEnabled(newvalue)
            elif variablename == 'xray_light_fault':
                self.setFlagBackground(self.xrayLightsFlag, not newvalue)
            elif variablename == 'shutter_light_fault':
                self.setFlagBackground(self.shutterLightsFlag, not newvalue)
            elif variablename == 'sensor2_fault':
                self.setFlagBackground(self.sensor2Flag, not newvalue)
            elif variablename == 'sensor1_fault':
                self.setFlagBackground(self.sensor1Flag, not newvalue)
            elif variablename == 'tube_position_fault':
                self.setFlagBackground(self.tubePositionFlag, not newvalue)
            elif variablename == 'vacuum_fault':
                self.setFlagBackground(self.opticsVacuumFlag, not newvalue)
            elif variablename == 'waterflow_fault':
                self.setFlagBackground(self.waterCoolingFlag, not newvalue)
            elif variablename == 'safety_shutter_fault':
                self.setFlagBackground(self.shutterMechanicsFlag, not newvalue)
            elif variablename == 'temperature_fault':
                self.setFlagBackground(self.tubeTemperatureFlag, not newvalue)
            elif variablename == 'relay_interlock_fault':
                self.setFlagBackground(self.interlockRelayFlag, not newvalue)
            elif variablename == 'door_fault':
                self.setFlagBackground(self.doorSensorFlag, not newvalue)
            elif variablename == 'filament_fault':
                self.setFlagBackground(self.filamentFlag, not newvalue)
            elif variablename == 'tube_warmup_needed':
                self.setFlagBackground(self.warmupFlag, not newvalue)
            elif variablename == 'interlock':
                self.setFlagBackground(self.interlockFlag, newvalue)
                self.shutterPushButton.setEnabled(newvalue)
            elif variablename == 'overridden':
                self.setFlagBackground(self.overriddenFlag, not newvalue)
            elif variablename == '_auxstatus':
                self.statusLabel.setText(device.get_variable('_status')+'\n('+newvalue+')')
            elif variablename == '_status':
                self.statusLabel.setText(newvalue+'\n('+device.get_variable('_auxstatus')+')')
                if newvalue == 'Power off':
                    self.xraysOnPushButton.setEnabled(True)
                    self.warmUpPushButton.setEnabled(True)
                    self.warmUpPushButton.setChecked(False)
                    self.shutterPushButton.setEnabled(device.get_variable('interlock'))
                    self.powerOffPushButton.setEnabled(False)
                    self.standbyPushButton.setEnabled(True)
                    self.fullPowerPushButton.setEnabled(False)
                elif newvalue == 'Low power':
                    self.xraysOnPushButton.setEnabled(False)
                    self.warmUpPushButton.setEnabled(False)
                    self.warmUpPushButton.setChecked(False)
                    self.shutterPushButton.setEnabled(device.get_variable('interlock'))
                    self.powerOffPushButton.setEnabled(True)
                    self.standbyPushButton.setEnabled(False)
                    self.fullPowerPushButton.setEnabled(True)
                elif newvalue == 'Full power':
                    self.xraysOnPushButton.setEnabled(False)
                    self.warmUpPushButton.setEnabled(False)
                    self.warmUpPushButton.setChecked(False)
                    self.shutterPushButton.setEnabled(device.get_variable('interlock'))
                    self.powerOffPushButton.setEnabled(True)
                    self.standbyPushButton.setEnabled(True)
                    self.fullPowerPushButton.setEnabled(False)
                elif newvalue == 'X-rays off':
                    self.xraysOnPushButton.setEnabled(True)
                    self.warmUpPushButton.setEnabled(False)
                    self.warmUpPushButton.setChecked(False)
                    self.shutterPushButton.setEnabled(False)
                    self.powerOffPushButton.setEnabled(False)
                    self.standbyPushButton.setEnabled(False)
                    self.fullPowerPushButton.setEnabled(False)
                elif newvalue == 'Going to stand-by':
                    self.xraysOnPushButton.setEnabled(False)
                    self.warmUpPushButton.setEnabled(False)
                    self.warmUpPushButton.setChecked(False)
                    self.shutterPushButton.setEnabled(device.get_variable('interlock'))
                    self.powerOffPushButton.setEnabled(True)
                    self.standbyPushButton.setEnabled(False)
                    self.fullPowerPushButton.setEnabled(False)
                elif newvalue == 'Ramping up':
                    self.xraysOnPushButton.setEnabled(False)
                    self.warmUpPushButton.setEnabled(False)
                    self.warmUpPushButton.setChecked(False)
                    self.shutterPushButton.setEnabled(device.get_variable('interlock'))
                    self.powerOffPushButton.setEnabled(True)
                    self.standbyPushButton.setEnabled(False)
                    self.fullPowerPushButton.setEnabled(False)
                elif newvalue == 'Powering down':
                    self.xraysOnPushButton.setEnabled(False)
                    self.warmUpPushButton.setEnabled(False)
                    self.warmUpPushButton.setChecked(False)
                    self.shutterPushButton.setEnabled(device.get_variable('interlock'))
                    self.powerOffPushButton.setEnabled(False)
                    self.standbyPushButton.setEnabled(False)
                    self.fullPowerPushButton.setEnabled(False)
                elif newvalue == 'Warming up':
                    self.xraysOnPushButton.setEnabled(False)
                    self.warmUpPushButton.setEnabled(True)
                    self.warmUpPushButton.setChecked(True)
                    self.shutterPushButton.setEnabled(device.get_variable('interlock'))
                    self.powerOffPushButton.setEnabled(False)
                    self.standbyPushButton.setEnabled(False)
                    self.fullPowerPushButton.setEnabled(False)
                else:
                    raise ValueError(newvalue)
        finally:
            self._updating_ui = False