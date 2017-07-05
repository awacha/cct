import logging
from typing import Union

from PyQt5 import QtWidgets, QtGui

from .detector_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.devices import Pilatus, Device, Motor
from ....core.utils.inhibitor import Inhibitor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Detector(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['pilatus']

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        self._updating_ui = Inhibitor()
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        pilatus = self.credo.get_device('pilatus')
        assert isinstance(pilatus, Pilatus)
        for var in pilatus.all_variables + ['_status']:
            self.onDeviceVariableChange(pilatus, var, pilatus.get_variable(var))
        self.trimPushButton.clicked.connect(self.onTrim)
        self.gainComboBox.currentTextChanged.connect(self.onGainChanged)
        self.gainComboBox.setCurrentIndex(self.gainComboBox.findText(pilatus.get_variable('gain') + 'G'))
        self.onGainChanged()
        self.thresholdSpinBox.setValue(int(pilatus.get_variable('threshold')))

    def setFlagBackground(self, flag: QtWidgets.QLabel, state: str):
        palette = flag.palette()
        assert isinstance(palette, QtGui.QPalette)
        if state == 'ok':
            palette.setColor(QtGui.QPalette.Window, QtGui.QColor('green'))
        elif state == 'warning':
            palette.setColor(QtGui.QPalette.Window, QtGui.QColor('orange'))
        else:
            palette.setColor(QtGui.QPalette.Window, QtGui.QColor('red'))
        flag.setPalette(palette)
        flag.setAutoFillBackground(True)

    def onTrim(self):
        threshold = self.thresholdSpinBox.value()
        gain = self.gainComboBox.currentText()
        pilatus = self.credo.get_device('pilatus')
        assert isinstance(pilatus, Pilatus)
        pilatus.set_threshold(threshold, gain)
        self.trimPushButton.setEnabled(False)
        self.gainComboBox.setEnabled(False)
        self.thresholdSpinBox.setEnabled(False)

    def onGainChanged(self):
        if self.gainComboBox.currentText() == 'lowG':
            self.thresholdSpinBox.setMinimum(6685)
            self.thresholdSpinBox.setMaximum(20202)
        elif self.gainComboBox.currentText() == 'midG':
            self.thresholdSpinBox.setMinimum(4425)
            self.thresholdSpinBox.setMaximum(14328)
        elif self.gainComboBox.currentText() == 'highG':
            self.thresholdSpinBox.setMinimum(3814)
            self.thresholdSpinBox.setMaximum(11614)
        else:
            if self.gainComboBox.currentText():
                raise ValueError(self.gainComboBox.currentText())

    def onDeviceVariableChange(self, device: Union[Device, Motor], variablename: str, newvalue):
        with self._updating_ui:
            assert isinstance(device, Pilatus)
            if variablename == 'gain':
                self.gainLabel.setText(newvalue)
            elif variablename == 'threshold':
                self.thresholdLabel.setText('{:.0f}'.format(newvalue))
            elif variablename == 'vcmp':
                self.vcmpLabel.setText('{:.3f}'.format(newvalue))
            elif variablename == 'trimfile':
                self.trimfileLabel.setText(newvalue.rsplit('/')[-1])
            elif variablename == 'wpix':
                self.imageSizeLabel.setText('{:d}×{:d}'.format(newvalue, device.get_variable('hpix')))
            elif variablename == 'hpix':
                self.imageSizeLabel.setText('{:d}×{:d}'.format(device.get_variable('wpix'), newvalue))
            elif variablename == 'sel_bank':
                self.selectedBankLabel.setText(str(newvalue))
            elif variablename == 'sel_module':
                self.selectedModuleLabel.setText(str(newvalue))
            elif variablename == 'sel_chip':
                self.selectedChipLabel.setText(str(newvalue))
            elif variablename == 'humidity0':
                self.humidity0Label.setText('{:.1f} %'.format(newvalue))
            elif variablename == 'humidity1':
                self.humidity1Label.setText('{:.1f} %'.format(newvalue))
            elif variablename == 'humidity2':
                self.humidity2Label.setText('{:.1f} %'.format(newvalue))
            elif variablename == 'temperature0':
                self.temperature0Label.setText('{:.1f} °C'.format(newvalue))
            elif variablename == 'temperature1':
                self.temperature1Label.setText('{:.1f} °C'.format(newvalue))
            elif variablename == 'temperature2':
                self.temperature2Label.setText('{:.1f} °C'.format(newvalue))
            elif variablename == 'nimages':
                self.nimagesLabel.setText(str(newvalue))
            elif variablename == 'cameradef':
                self.definitionFileLabel.setText(newvalue)
            elif variablename == 'cameraname':
                self.cameraNameLabel.setText(newvalue)
            elif variablename == 'cameraSN':
                self.serialNumberLabel.setText(newvalue)
            elif variablename == 'camstate':
                self.camstateLabel.setText(newvalue)
            elif variablename == 'targetfile':
                self.targetfileLabel.setText(newvalue)
            elif variablename == 'timeleft':
                self.timeleftLabel.setText('{:.1f} s'.format(newvalue))
            elif variablename == 'lastimage':
                self.lastimageLabel.setText(newvalue)
            elif variablename == 'masterPID':
                self.masterPIDLabel.setText(str(newvalue))
            elif variablename == 'controllingPID':
                self.controllingPIDLabel.setText(str(newvalue))
            elif variablename == 'pid':
                self.thisPIDLabel.setText(str(newvalue))
            elif variablename == 'exptime':
                self.exptimeLabel.setText('{:.3f} s'.format(newvalue))
            elif variablename == 'lastcompletedimage':
                self.lastcompletedimageLabel.setText(newvalue)
            elif variablename == 'shutterstate':
                self.shutterstateLabel.setText(newvalue)
            elif variablename == 'imgpath':
                self.imagePathLabel.setText(newvalue)
            elif variablename == 'imgmode':
                self.imgmodeLabel.setText(newvalue)
            elif variablename == 'expperiod':
                self.expperiodLabel.setText('{:.3f} s'.format(newvalue))
            elif variablename == 'tau':
                self.tauLabel.setText('{}'.format(newvalue))
            elif variablename == 'cutoff':
                self.cutoffLabel.setText(str(newvalue))
            elif variablename == 'diskfree':
                self.diskfreeLabel.setText('{:.2f} GB'.format(newvalue / 1024 / 1024))
            elif variablename == 'version':
                self.softwareVersionLabel.setText(newvalue)
            elif variablename == 'telemetry_date':
                pass
            elif variablename == '_status':
                self.statusLabel.setText(newvalue + '\n(' + str(device.get_variable('_auxstatus')) + ')')
                if newvalue == 'idle':
                    self.thresholdSpinBox.setEnabled(True)
                    self.gainComboBox.setEnabled(True)
                    self.trimPushButton.setEnabled(True)
