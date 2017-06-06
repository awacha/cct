from PyQt5 import QtWidgets, QtGui

from .motorconfig_ui import Ui_Form
from ....core.mixins import ToolWindow
from .....core.devices import TMCMCard
from .....core.devices.motor import Motor
from .....core.instrument.privileges import PRIV_MOTORCONFIG


class MotorConfig(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_privilege = PRIV_MOTORCONFIG
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        self.motor = kwargs.pop('motor')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo, required_devices=['Motor_'+self.motor.name])
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.warningIconLabel.setPixmap(
            QtGui.QIcon.fromTheme('dialog-warning').pixmap(
                48,48
            ))
        self.setWindowTitle('Configure Motor {}'.format(self.motor.name))
        self.applyPushButton.clicked.connect(self.onApply)
        self.calibratePushButton.clicked.connect(self.onCalibrate)
        self.resetPushButton.clicked.connect(self.onReset)
        self.motorNameLabel.setText(self.motor.name)
        self.controllerNameLabel.setText(self.motor._controller.name)
        self.onReset()
        self.leftLimitDoubleSpinBox.valueChanged.connect(self.onSoftLimitChanged)
        self.rightLimitDoubleSpinBox.valueChanged.connect(self.onSoftLimitChanged)
        self.pulseDivisorSpinBox.valueChanged.connect(self.calculateSpeedAndAccel)
        self.rampDivisorSpinBox.valueChanged.connect(self.calculateSpeedAndAccel)
        self.microstepExponentSpinBox.valueChanged.connect(self.calculateSpeedAndAccel)
        self.rawMaxSpeedSpinBox.valueChanged.connect(self.calculateSpeedAndAccel)
        self.rawMaxAccelSpinBox.valueChanged.connect(self.calculateSpeedAndAccel)
        for widget in [self.driveRMSCurrentDoubleSpinBox,
                       self.standbyRMSCurrentDoubleSpinBox,
                       self.freewheelingDelayDoubleSpinBox,
                       self.pulseDivisorSpinBox,
                       self.rampDivisorSpinBox,
                       self.microstepExponentSpinBox,
                       self.rawMaxSpeedSpinBox,
                       self.rawMaxAccelSpinBox,
                       self.leftSwitchEnabledCheckBox,
                       self.rightSwitchEnabledCheckBox,
                       self.leftLimitDoubleSpinBox,
                       self.rightLimitDoubleSpinBox]:
            if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                widget.valueChanged.connect(self.onWidgetChanged)
            elif isinstance(widget, QtWidgets.QCheckBox):
                widget.toggled.connect(self.onWidgetChanged)
            else:
                raise TypeError(type(widget))

    def onWidgetChanged(self):
        pal=self.sender().palette()
        pal.setColor(pal.Base, QtGui.QColor('yellow'))
        self.sender().setPalette(pal)

    def resetEntryBackgrounds(self):
        for widget in [self.driveRMSCurrentDoubleSpinBox,
                       self.standbyRMSCurrentDoubleSpinBox,
                       self.freewheelingDelayDoubleSpinBox,
                       self.pulseDivisorSpinBox,
                       self.rampDivisorSpinBox,
                       self.microstepExponentSpinBox,
                       self.rawMaxSpeedSpinBox,
                       self.rawMaxAccelSpinBox,
                       self.leftSwitchEnabledCheckBox,
                       self.rightSwitchEnabledCheckBox,
                       self.leftLimitDoubleSpinBox,
                       self.rightLimitDoubleSpinBox]:
            pal = widget.palette()
            pal.setColor(pal.Base, QtGui.QColor('white'))
            widget.setPalette(pal)

    def onSoftLimitChanged(self):
        self.leftLimitDoubleSpinBox.setMaximum(self.rightLimitDoubleSpinBox.value())
        self.rightLimitDoubleSpinBox.setMinimum(self.leftLimitDoubleSpinBox.value())
        self.calibrationDoubleSpinBox.setMinimum(self.leftLimitDoubleSpinBox.value())
        self.calibrationDoubleSpinBox.setMaximum(self.rightLimitDoubleSpinBox.value())

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        if motor.name != self.motor.name:
            return
        self.currentPositionLabel.setText('{:.4f}'.format(newposition))
        return False

    def onApply(self):
        changes = {}
        for widget, attribute in [
            (self.driveRMSCurrentDoubleSpinBox, 'maxcurrent'),
            (self.standbyRMSCurrentDoubleSpinBox, 'standbycurrent'),
            (self.freewheelingDelayDoubleSpinBox, 'freewheelingdelay'),
            (self.pulseDivisorSpinBox, 'pulsedivisor'),
            (self.rampDivisorSpinBox,'rampdivisor'),
            (self.microstepExponentSpinBox,'microstepresolution'),
            (self.rawMaxSpeedSpinBox,'maxspeedraw'),
            (self.rawMaxAccelSpinBox,'maxaccelerationraw'),
            (self.leftSwitchEnabledCheckBox,'leftswitchenable'),
            (self.rightSwitchEnabledCheckBox,'rightswitchenable'),
            (self.leftLimitDoubleSpinBox,'softleft'),
            (self.rightLimitDoubleSpinBox,'softright')]:
            assert isinstance(widget, QtWidgets.QWidget)
            if widget.palette().color(QtGui.QPalette.Base)!=QtGui.QColor('yellow'):
                continue
            if isinstance(widget, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
                changes[attribute]=widget.value()
            elif isinstance(widget, QtWidgets.QCheckBox):
                changes[attribute]=widget.isChecked()
        result = QtWidgets.QMessageBox.warning(
            self,
            'Confirm changes',
            'Do you really want to commit the following changes to motor {}?\n'.format(self.motor.name)+
            '\n'.join(['{}: {} -> {}'.format(attr, self.motor.get_variable(attr), changes[attr])
                       for attr in sorted(changes)]),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
        )
        if result == QtWidgets.QMessageBox.Yes:
            for attr in changes:
                self.motor.set_variable(attr, changes[attr])
        self.resetEntryBackgrounds()

    def onReset(self):
        assert isinstance(self.motor._controller, TMCMCard)
        self.currentPositionLabel.setText('{:.4f}'.format(self.motor.where()))
        self.driveRMSCurrentDoubleSpinBox.setMinimum(0)
        self.driveRMSCurrentDoubleSpinBox.setMaximum(self.motor._controller.top_RMS_current)
        self.driveRMSCurrentDoubleSpinBox.setValue(self.motor.get_variable('maxcurrent'))
        self.standbyRMSCurrentDoubleSpinBox.setMinimum(0)
        self.standbyRMSCurrentDoubleSpinBox.setMaximum(self.motor._controller.top_RMS_current)
        self.standbyRMSCurrentDoubleSpinBox.setValue(self.motor.get_variable('standbycurrent'))
        self.freewheelingDelayDoubleSpinBox.setMinimum(0)
        self.freewheelingDelayDoubleSpinBox.setMaximum(65.535)
        self.freewheelingDelayDoubleSpinBox.setValue(self.motor.get_variable('freewheelingdelay'))
        self.pulseDivisorSpinBox.setMinimum(0)
        self.pulseDivisorSpinBox.setMaximum(13)
        self.pulseDivisorSpinBox.setValue(self.motor.get_variable('pulsedivisor'))
        self.rampDivisorSpinBox.setMinimum(0)
        self.rampDivisorSpinBox.setMaximum(13)
        self.rampDivisorSpinBox.setValue(self.motor.get_variable('rampdivisor'))
        self.microstepExponentSpinBox.setMinimum(0)
        self.microstepExponentSpinBox.setMaximum(self.motor._controller.max_microsteps)
        self.microstepExponentSpinBox.setValue(self.motor.get_variable('microstepresolution'))
        self.leftLimitDoubleSpinBox.setMinimum(-1e6)
        self.leftLimitDoubleSpinBox.setMaximum(1e6)
        self.leftLimitDoubleSpinBox.setValue(self.motor.get_variable('softleft'))
        self.rightLimitDoubleSpinBox.setMinimum(-1e6)
        self.rightLimitDoubleSpinBox.setMaximum(1e6)
        self.rightLimitDoubleSpinBox.setValue(self.motor.get_variable('softright'))
        self.onSoftLimitChanged()
        self.leftSwitchEnabledCheckBox.setChecked(self.motor.get_variable('leftswitchenable'))
        self.rightSwitchEnabledCheckBox.setChecked(self.motor.get_variable('rightswitchenable'))
        self.rawMaxSpeedSpinBox.setMinimum(0)
        self.rawMaxSpeedSpinBox.setMaximum(2047)
        self.rawMaxSpeedSpinBox.setValue(self.motor.get_variable('maxspeedraw'))
        self.rawMaxAccelSpinBox.setMinimum(0)
        self.rawMaxAccelSpinBox.setMaximum(2048)
        self.rawMaxAccelSpinBox.setValue(self.motor.get_variable('maxaccelerationraw'))
        self.resetEntryBackgrounds()
        self.calculateSpeedAndAccel()

    def calculateSpeedAndAccel(self):
        assert isinstance(self.motor._controller, TMCMCard)
        nustep=2**self.microstepExponentSpinBox.value()
        ustepsize=self.motor._controller.full_step_size/nustep
        maxustepfreq=self.motor._controller.clock_frequency*self.rawMaxSpeedSpinBox.value()/(2.0**self.pulseDivisorSpinBox.value()*2048*32)
        maxstepfreq=maxustepfreq/nustep
        maxspeed = maxstepfreq* self.motor._controller.full_step_size
        maxaccel = self.motor._controller.clock_frequency**2*self.rawMaxAccelSpinBox.value()/(
            2.0**(self.pulseDivisorSpinBox.value()+
                  self.rampDivisorSpinBox.value()+
                  29+
                  self.microstepExponentSpinBox.value()))*self.motor._controller.full_step_size
        self.nMicrostepLabel.setText('{:d}'.format(nustep))
        self.microStepSizeLabel.setText('{:.4f}'.format(1000*ustepsize))
        self.maximumSpeedLabel.setText('{:.4f}'.format(maxspeed))
        self.maxMicrostepFrequencyLabel.setText('{:.4f}'.format(maxustepfreq))
        self.maxFullstepFrequencyLabel.setText('{:.4f}'.format(maxstepfreq))
        self.accelerationLabel.setText('{:.4f}'.format(maxaccel))
        self.accelTimeLabel.setText('{:.4f}'.format(maxspeed/maxaccel))
        self.accelLengthLabel.setText('{:.4f}'.format(maxspeed**2/2/maxaccel))

    def onCalibrate(self):
        self.motor.calibrate(self.calibrationDoubleSpinBox.value())
        pal=self.calibrationDoubleSpinBox.palette()
        pal.setColor(pal.Base, QtGui.QColor('white'))
        self.calibrationDoubleSpinBox.setPalette(pal)
