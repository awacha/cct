from typing import Any
import logging

from PyQt5 import QtWidgets, QtGui
from ...utils.window import WindowRequiresDevices
from .tecnoware_ui import Ui_Form
from ....core2.devices.ups.tecnoware import TecnowareEvoDSPPlus

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class TecnowareUPS(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicenames = ['TecnowareEvoDSPPlus']
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def ups(self) -> TecnowareEvoDSPPlus:
        return [dev for dev in self.instrument.devicemanager if dev.devicename == 'TecnowareEvoDSPPlus'][0]

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.ups())
        for variable in self.ups().keys():
            if variable.startswith('flag.'):
                try:
                    toolbutton: QtWidgets.QPushButton = getattr(self, variable.split('.')[1]+'PushButton')
                    toolbutton.setEnabled(False)
                    toolbutton.toggled.connect(self.onFlagButtonToggled)
                except AttributeError:
                    pass
            try:
                self.onVariableChanged(variable, self.ups()[variable], self.ups()[variable])
            except ups.DeviceError:
                pass

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        logger.debug(f'{name}: {prevvalue} -> {newvalue}')
        if name == '__status__':
            pass
        elif name == '__auxstatus__':
            pass
        elif name == 'inputvoltage':
            self.inputVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'inputfaultvoltage':
            self.faultVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'outputvoltage':
            self.outputVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'outputcurrentpercentage':
            try:
                ratedcurrent = self.ups()['ratedcurrent']
            except self.ups().DeviceError:
                pass
            else:
                self.currentUsageLabel.setText(f'{ratedcurrent*newvalue/100.:.3f} A ({newvalue:.0f} %)')
        elif name == 'inputfrequency':
            self.inputFrequencyLabel.setText(f'{newvalue:.2f} Hz')
        elif name == 'batteryvoltage':
            self.batteryVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'temperature':
            self.temperatureLabel.setText(f'{newvalue:.2f} °C')
        elif name == 'ratedvoltage':
            self.ratedVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'ratedcurrent':
            self.ratedCurrentLabel.setText(f'{newvalue:.2f} A')
        elif name == 'ratedbatteryvoltage':
            self.ratedBatteryVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'ratedfrequency':
            self.ratedFrequencyLabel.setText(f'{newvalue:.2f} Hz')
        elif name.startswith('flag.'):
            flagname = name.split('.')[1]
            try:
                toolbutton:QtWidgets.QPushButton = getattr(self, flagname+'PushButton')
                toolbutton.blockSignals(True)
                toolbutton.setChecked(bool(newvalue))
                toolbutton.setEnabled(True)
                toolbutton.blockSignals(False)
            except AttributeError:
                pass
        else:
            for varname, widget, goodtext, badtext, goodbool in [
                ('utilityfail', self.utilityFailedLabel, 'Grid power OK', 'Grid power out', False),
                ('batterylow', self.batteryLowLabel, 'Battery OK', 'Battery LOW', False),
                ('bypassactive', self.bypassLabel, 'Bypass not activated', 'Bypass Active', False),
                ('upsfailed', self.upsFailedLabel, 'UPS OK', 'UPS failed', False),
                ('testinprogress', self.testInProgressLabel, 'No test in progress', 'Test in progress', False),
                ('shutdownactive', self.shutdownInProgressLabel, "Won't shut down", 'Will shut down soon', False),
                ('beeperon', self.beeperOnLabel, "Beeper off", 'Beeper on', False),
            ]:
                if name == varname:
                    good = (newvalue == goodbool)
                    widget.setText(goodtext if good else badtext)
                    widget.setAutoFillBackground(True)
                    pal = widget.palette()
                    pal.setColor(pal.Window, QtGui.QColor('lightgreen' if good else 'red'))
                    widget.setPalette(pal)

    def onFlagButtonToggled(self, state: bool):
        flagbutton: QtWidgets.QPushButton = self.sender()
        flagname = flagbutton.objectName().replace('PushButton', '')
        self.ups().issueCommand('setflag' if state else 'clearflag', flagname)