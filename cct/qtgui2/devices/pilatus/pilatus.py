from typing import Any, Final, Dict, Tuple
import logging

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Slot

from ...utils.window import WindowRequiresDevices
from .pilatus_ui import Ui_Form
from ....core2.devices.detector.pilatus.frontend import PilatusDetector, PilatusGain, PilatusBackend
from ....core2.devices.device.frontend import DeviceFrontend

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# humidity & temperature

# system information:
#   wpix, hpix, cameraname, cameraSN, imgmode, version, remote control enabled (controllingPID == pid)

# file system:
#   imgpath, diskfree

# threshold trimming:
#   - gain, threshold, vcmp, trimfile

# cutoff
#   - cutoff, tau

# exposure
#   - expperiod, exptime, nimages, timeleft, starttime, lastcompletedimage, lastimage, targetfile


class PilatusDetectorUI(WindowRequiresDevices, QtWidgets.QWidget, Ui_Form):
    required_devicenames = ['PilatusDetector']
    thresholdsettings: Final[Dict[str, Tuple[float, PilatusGain]]] = {
        'Cu': (4024, PilatusGain.High),
        'Ag': (11082, PilatusGain.Low),
        'Cr': (3814, PilatusGain.High),
        'Fe': (3814, PilatusGain.High),  # yes, same as Cr
        'Mo': (8740, PilatusGain.Low),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.gainComboBox.addItems([p.value for p in PilatusGain])
        self.gainComboBox.setCurrentIndex(0)
        self.gainComboBox.setCurrentIndex(self.gainComboBox.findText(self.instrument.devicemanager.detector()['gain']))
        self.thresholdDoubleSpinBox.setValue(self.instrument.devicemanager.detector()['threshold'])
        det = self.instrument.devicemanager.detector()
        for variable in ['gain', 'threshold', 'vcmp', 'tau', 'cutoff',
                         'humidity', 'temperature', 'temperaturelimits', 'humiditylimits',
                         'cameradef', 'cameraname', 'cameraSN',  'imgmode', 'wpix', 'hpix',  'version',
                         'masterPID', 'controllingPID', 'pid',
                         'imgpath', 'diskfree',
                         'exptime', 'nimages', 'expperiod', 'starttime', '__status__']:
            logger.debug(f'Getting variable {variable}')
            try:
                self.onVariableChanged(variable, det[variable], None)
            except DeviceFrontend.DeviceError:
                # this variable has not yet been updated
                logger.warning(f'Variable not yet updated: {variable}')
                pass

    @Slot(bool, name='on_setAgToolButton_clicked')
    @Slot(bool, name='on_setCrToolButton_clicked')
    @Slot(bool, name='on_setCuToolButton_clicked')
    @Slot(bool, name='on_setFeToolButton_clicked')
    @Slot(bool, name='on_setMoToolButton_clicked')
    def onQuickTrim(self, checked: bool):
        if self.sender() is self.setAgToolButton:
            threshold, gain = self.thresholdsettings['Ag']
        elif self.sender() is self.setCrToolButton:
            threshold, gain = self.thresholdsettings['Cr']
        elif self.sender() is self.setCuToolButton:
            threshold, gain = self.thresholdsettings['Cu']
        elif self.sender() is self.setFeToolButton:
            threshold, gain = self.thresholdsettings['Fe']
        elif self.sender() is self.setMoToolButton:
            threshold, gain = self.thresholdsettings['Mo']
        else:
            assert False
        self.gainComboBox.setCurrentIndex(self.gainComboBox.findText(gain.value))
        self.thresholdDoubleSpinBox.setValue(threshold)
        self.trimPushButton.click()

    @Slot(int, name='on_gainComboBox_currentIndexChanged')
    def updateThresholdLimits(self, currentIndex: int):
        if self.gainComboBox.currentIndex() < 0:
            return
        gain = PilatusGain(self.gainComboBox.currentText())
        detector = self.instrument.devicemanager.detector()
        assert isinstance(detector, PilatusDetector)
        self.thresholdDoubleSpinBox.setRange(*detector.thresholdLimits(gain))

    @Slot(bool, name='on_trimPushButton_clicked')
    def onTrimButtonClicked(self, checked: bool):
        detector = self.instrument.devicemanager.detector()
        assert isinstance(detector, PilatusDetector)
        detector.trim(self.thresholdDoubleSpinBox.value(), PilatusGain(self.gainComboBox.currentText()))

    @Slot(str, object, object, name='onVariableChanged')
    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        det: PilatusDetector = self.instrument.devicemanager.detector()
        if name == '__status__':
            self.trimPushButton.setEnabled(newvalue == PilatusBackend.Status.Idle)
            self.statusLabel.setText(newvalue)
        elif name == 'gain':
            self.gainComboBox.setCurrentIndex(self.gainComboBox.findText(det['gain']))
            self.thresholdDoubleSpinBox.setValue(det['threshold'])
            self.gainLabel.setText(newvalue)
        elif name == 'threshold':
            self.thresholdDoubleSpinBox.setValue(det['threshold'])
            self.thresholdLabel.setText(f'{newvalue:.0f} eV')
        elif name == 'vcmp':
            self.vcmpLabel.setText(f'{newvalue:.3f} V')
        elif name in ['wpix', 'hpix']:
            try:
                self.geometryLabel.setText(f'{det["wpix"]} × {det["hpix"]} (pixels X × Y)')
            except DeviceFrontend.DeviceError:
                pass
        elif name in ['humidity', 'humiditylimits']:
            try:
                humidity = det['humidity']
                humiditylimits = det['humiditylimits']
            except det.DeviceError:
                pass
            else:
                for label, value, (lowlim, uplim) in zip(
                        [self.humidity0Label, self.humidity1Label, self.humidity2Label],
                        humidity, humiditylimits):
                    label.setText(f'{value:.1f} %')
                    label.setAutoFillBackground(True)
                    pal = label.palette()
                    pal.setColor(QtGui.QPalette.Window, QtGui.QColor('red' if (value < lowlim) or (value > uplim) else 'lightgreen'))
                    label.setPalette(pal)
        elif name in ['temperature', 'temperaturelimits']:
            try:
                temperature = det['temperature']
                temperaturelimits = det['temperaturelimits']
            except det.DeviceError:
                pass
            else:
                for label, value, (lowlim, uplim) in zip(
                        [self.temperature0Label, self.temperature1Label, self.temperature2Label],
                        temperature, temperaturelimits):
                    label.setText(f'{value:.1f} °C')
                    label.setAutoFillBackground(True)
                    pal = label.palette()
                    pal.setColor(QtGui.QPalette.Window, QtGui.QColor('red' if (value < lowlim) or (value > uplim) else 'lightgreen'))
                    label.setPalette(pal)
        elif name == 'cameradef':
            pass
        elif name == 'nimages':
            pass
        elif name == 'cameraname':
            self.cameraNameLabel.setText(newvalue)
        elif name == 'cameraSN':
            self.cameraSNLabel.setText(newvalue)
        elif name == 'imgmode':
            self.imgmodeLabel.setText(newvalue)
        elif name == 'version':
            self.versionLabel.setText(newvalue)
        elif name in ['controllingPID', 'pid']:
            try:
                haverights = det['controllingPID'] == det['pid']
            except DeviceFrontend.DeviceError:
                self.remoteControlLabel.setText('--')
                self.remoteControlLabel.setAutoFillBackground(False)
            else:
                self.remoteControlLabel.setText('YES' if haverights else 'NO')
                self.remoteControlLabel.setAutoFillBackground(True)
                pal = self.remoteControlLabel.palette()
                pal.setColor(QtGui.QPalette.Window, QtGui.QColor('lightgreen' if haverights else 'red'))
                self.remoteControlLabel.setPalette(pal)
        elif name == 'tau':
            self.tauLabel.setText(f'{newvalue*1e9:.1f} ns')
        elif name == 'cutoff':
            self.cutoffLabel.setText(f'{newvalue} counts')
        elif name == 'imgpath':
            self.imgpathLabel.setText(newvalue)
        elif name == 'diskfree':
            self.diskfreeLabel.setText(f'{newvalue/1024/1024:.3f} GB')



