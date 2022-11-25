from typing import Any
import logging

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Slot

from ...utils.window import WindowRequiresDevices
from .keen800_ui import Ui_Form

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Keen80UPS(WindowRequiresDevices, QtWidgets.QWidget, Ui_Form):
    required_devicenames = ['Keen800']
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        ups = [dev for dev in self.instrument.devicemanager if dev.devicename == 'Keen800'][0]
        for variable in ups.keys():
            try:
                self.onVariableChanged(variable, ups[variable], ups[variable])
            except ups.DeviceError:
                pass

    @Slot(str, object, object)
    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        logger.debug(f'{name}: {prevvalue} -> {newvalue}')
        ups = [dev for dev in self.instrument.devicemanager if dev.devicename == 'Keen800'][0]
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
                ratedcurrent = ups['ratedcurrent']
            except ups.DeviceError:
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
