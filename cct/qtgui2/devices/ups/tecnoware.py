import logging
from typing import Any

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Slot

from .tecnoware_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.devices.ups.tecnoware import TecnowareEvoDSPPlus

logger = logging.getLogger(__name__)
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
        for variable in self.ups().keys():
            if variable.startswith('flag.'):
                try:
                    toolbutton: QtWidgets.QPushButton = getattr(self, variable.split('.')[1] + 'PushButton')
                    toolbutton.setEnabled(False)
                    toolbutton.toggled.connect(self.onFlagButtonToggled)
                except AttributeError:
                    pass
            try:
                self.onVariableChanged(variable, self.ups()[variable], self.ups()[variable])
            except TecnowareEvoDSPPlus.DeviceError:
                pass

    @Slot(str, object, object)
    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        logger.debug(f'{name}: {prevvalue} -> {newvalue}')
        if name == '__status__':
            pass
        elif name == '__auxstatus__':
            pass
        elif name == 'inputvoltage':
            self.inputVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'outputvoltage':
            self.outputVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'outputcurrent':
            self.currentUsageLabel.setText(f'{newvalue:.1f} A')
        elif name == 'inputfrequency':
            self.inputFrequencyLabel.setText(f'{newvalue:.2f} Hz')
        elif name == 'batteryvoltage':
            self.batteryVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'ratedvoltage':
            self.ratedVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'ratedcurrent':
            self.ratedCurrentLabel.setText(f'{newvalue:.2f} A')
        elif name == 'ratedbatteryvoltage':
            self.ratedBatteryVoltageLabel.setText(f'{newvalue:.2f} V')
        elif name == 'ratedfrequency':
            self.ratedFrequencyLabel.setText(f'{newvalue:.2f} Hz')
        elif name == 'modelname':
            self.modelnameLabel.setText(f'{newvalue:}')
        elif name == 'batterycount':
            self.batterycountLabel.setText(f'{newvalue:}')
        elif name == 'firmwareversion':
            self.firmwareversionLabel.setText(f'{newvalue:}')
        elif name == 'hardwareversion':
            self.hardwareversionLabel.setText(f'{newvalue:}')
        elif name == 'batterycapacity_ah':
            self.batterycapacityAHLabel.setText(f'{newvalue:} Ah')
        elif name == 'upsmode':
            self.statusLabel.setText(f'{newvalue:}')
        elif name == 'batterycapacity':
            self.batterycapacityLabel.setText(f'{newvalue:.0f} %')
        elif name == 'batteryremaintime':
            self.remainingtimeLabel.setText(f'{newvalue:.0f} min')
        elif name == 'outputloadpercentage':
            self.loadlevelLabel.setText(f'{newvalue:0} %')
        elif name == 'temperature.pfc':
            self.temperaturePFCLabel.setText(f'{newvalue:.0f}°C')
        elif name == 'temperature.ambient':
            self.temperatureAmbientLabel.setText(f'{newvalue:.0f}°C')
        elif name == 'temperature.charger':
            self.temperatureChargerLabel.setText(f'{newvalue:.0f}°C')
        elif name.startswith('flag.'):
            flagname = name.split('.')[1]
            try:
                toolbutton: QtWidgets.QPushButton = getattr(self, flagname + 'PushButton')
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
            ]:
                if name == varname:
                    good = (newvalue == goodbool)
                    widget.setText(goodtext if good else badtext)
                    widget.setAutoFillBackground(True)
                    pal = widget.palette()
                    pal.setColor(pal.Window, QtGui.QColor('lightgreen' if good else 'red'))
                    widget.setPalette(pal)

    @Slot(bool)
    def onFlagButtonToggled(self, state: bool):
        flagbutton: QtWidgets.QPushButton = self.sender()
        flagname = flagbutton.objectName().replace('PushButton', '')
        self.ups().issueCommand('setflag' if state else 'clearflag', flagname)
