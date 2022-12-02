from typing import Optional, List, Tuple, Callable, Any
import logging


from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Slot

from .motorconfig_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.auth.privilege import Privilege
from ....core2.devices.motor.trinamic.conversion import UnitConverter
from ....core2.devices.motor.trinamic.frontend import TrinamicMotor

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AdvancedMotorConfig(WindowRequiresDevices, QtWidgets.QWidget, Ui_Form):
    required_privileges = [Privilege.MotorConfiguration]
    connect_all_motors = True
    motorname: Optional[str] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.warningPictureLabel.setPixmap(QtGui.QIcon.fromTheme('dialog-warning').pixmap(64,64))
        self.applyPushButton.clicked.connect(self.applyChanges)
        self.resetPushButton.clicked.connect(self.resetChanges)
        self.motorSelectorComboBox.currentIndexChanged.connect(self.onMotorSelected)
        self.maxSpeedSpinBox.valueChanged.connect(self.onRawPhysSpinboxChanged)
        self.maxSpeedDoubleSpinBox.valueChanged.connect(self.onRawPhysSpinboxChanged)
        self.maxAccelerationSpinBox.valueChanged.connect(self.onRawPhysSpinboxChanged)
        self.maxAccelerationDoubleSpinBox.valueChanged.connect(self.onRawPhysSpinboxChanged)
        self.maxCurrentSpinBox.valueChanged.connect(self.onRawPhysSpinboxChanged)
        self.maxCurrentDoubleSpinBox.valueChanged.connect(self.onRawPhysSpinboxChanged)
        self.standbyCurrentSpinBox.valueChanged.connect(self.onRawPhysSpinboxChanged)
        self.standbyCurrentDoubleSpinBox.valueChanged.connect(self.onRawPhysSpinboxChanged)

        # pulse divisor, ramp divisor and microstep resolution affect the raw <-> phys conversion of speed and
        # acceleration quantities. Therefore whenever they are updated, the raw -> phys calculation is to be redone.
        self.pulseDivisorSpinBox.valueChanged.connect(self.recalculateRawToPhys)
        self.rampDivisorSpinBox.valueChanged.connect(self.recalculateRawToPhys)
        self.microstepResolutionSpinBox.valueChanged.connect(self.recalculateRawToPhys)
        self.updateMotorSelector()

    def updateMotorSelector(self):
        if not hasattr(self, 'motorSelectorComboBox'):
            # can happen before setupUi() is called
            return None
        currentmotor = self.motorSelectorComboBox.currentText()
        self.motorSelectorComboBox.blockSignals(True)
        try:
            self.motorSelectorComboBox.clear()
            self.motorSelectorComboBox.addItems(sorted([mot.name for mot in self.instrument.motors.iterMotors()]))
            self.motorSelectorComboBox.setCurrentIndex(self.motorSelectorComboBox.findText(currentmotor))
        finally:
            self.motorSelectorComboBox.blockSignals(False)
        if self.motorSelectorComboBox.currentText() != currentmotor:
            self.motorSelectorComboBox.setCurrentIndex(0)

    @Slot(str)
    def onMotorRemoved(self, motorname: str):
        self.updateMotorSelector()

    @Slot(float)
    def onMotorStarted(self, startposition: float):
        self.entryVerticalLayout.setEnabled(False)

    @Slot(bool, float)
    def onMotorStopped(self, success: bool, endposition: float):
        self.entryVerticalLayout.setEnabled(True)

    @Slot()
    def onMotorOnLine(self):
        self.updateMotorSelector()

    @Slot()
    def onMotorOffLine(self):
        self.updateMotorSelector()

    @Slot()
    def onNewMotor(self, motorname: str):
        self.updateMotorSelector()

    @Slot()
    def onMotorSelected(self):
        if self.motorname is not None:
            self.disconnectMotor(self.motorname)
            self.motorname = None
        if self.motorSelectorComboBox.currentIndex() < 0:
            self.entryVerticalLayout.setEnabled(False)
        else:
            self.motorname = self.motorSelectorComboBox.currentText()
            self.connectMotor(self.motorSelectorComboBox.currentText())
            self.entryVerticalLayout.setEnabled(True)
        self.resetChanges()

    @Slot()
    def applyChanges(self):
        motor = self.instrument.motors.get(self.motorSelectorComboBox.currentText())
        axis = motor.axis
        controller: TrinamicMotor = motor.controller
        changed: List[Tuple[str, Any, Any, Callable[[int, Any], Any]]] = []
        for widgetvalue, variablename, setfunc in [
            (self.pulseDivisorSpinBox.value(), 'pulsedivisor', controller.setPulseDivisor),
            (self.rampDivisorSpinBox.value(), 'rampdivisor', controller.setRampDivisor),
            (self.microstepResolutionSpinBox.value(), 'microstepresolution', controller.setMicroStepResolution),
            (self.enableLeftSwitchCheckBox.isChecked(), 'leftswitchenable', controller.setLeftSwitchEnable),
            (self.enableRightSwitchCheckBox.isChecked(), 'rightswitchenable', controller.setRightSwitchEnable),
            (self.freewheelingDelayDoubleSpinBox.value(), 'freewheelingdelay', controller.setFreewheelingDelay),
            (self.maxSpeedSpinBox.value(), 'maxspeed:raw', controller.setMaxSpeed),
            (self.maxAccelerationSpinBox.value(), 'maxacceleration:raw', controller.setMaxAcceleration),
            (self.maxCurrentSpinBox.value(), 'maxcurrent:raw', controller.setMaxCurrent),
            (self.standbyCurrentSpinBox.value(), 'standbycurrent:raw', controller.setStandbyCurrent),
        ]:
            if widgetvalue != motor.get(variablename):
                changed.append((variablename, widgetvalue, motor.get(variablename), setfunc))
        if changed:
            result = QtWidgets.QMessageBox.warning(
                self.window(), 'Updating motor parameters',
                'You are about to update the following motor parameters:\n'+'\n'.join(
                    [f'{varname}: {oldvalue} -> {widgetvalue}'
                     for varname, widgetvalue, oldvalue, setfunc in changed]
                ) + '\nAre you really sure?',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
            )
            if result == QtWidgets.QMessageBox.StandardButton.Yes:
                for varname, widgetvalue, oldvalue, setfunc in changed:
                    logger.info(
                        f'Updating variable {varname} of motor {motor.name} ({controller.name}:{axis}) from {oldvalue} '
                        f'to {widgetvalue}')
                    setfunc(axis, widgetvalue)

    @Slot()
    def resetChanges(self):
        if self.motorSelectorComboBox.currentIndex() < 0:
            return
        mot = self.instrument.motors.get(self.motorSelectorComboBox.currentText())
        self.controllerNameLabel.setText(mot.controllername)
        self.axisIndexLabel.setText(str(mot.axis))
        # avoid automatic updating of dependent spin boxes
        for widget in [self.pulseDivisorSpinBox, self.rampDivisorSpinBox, self.microstepResolutionSpinBox,
                       self.enableLeftSwitchCheckBox, self.enableRightSwitchCheckBox,
                       self.freewheelingDelayDoubleSpinBox, self.maxSpeedSpinBox, self.maxCurrentSpinBox,
                       self.maxAccelerationSpinBox, self.standbyCurrentSpinBox, self.maxSpeedDoubleSpinBox,
                       self.maxCurrentDoubleSpinBox, self.maxAccelerationDoubleSpinBox,
                       self.standbyCurrentDoubleSpinBox]:
            widget.blockSignals(True)
        try:
            self.pulseDivisorSpinBox.setRange(0, 13)
            self.pulseDivisorSpinBox.setSingleStep(1)
            self.pulseDivisorSpinBox.setValue(mot.get('pulsedivisor'))
            self.rampDivisorSpinBox.setRange(0, 13)
            self.rampDivisorSpinBox.setSingleStep(1)
            self.rampDivisorSpinBox.setValue(mot.get('rampdivisor'))
            self.microstepResolutionSpinBox.setRange(0, 8)
            self.microstepResolutionSpinBox.setSingleStep(1)
            self.microstepResolutionSpinBox.setValue(mot.get('microstepresolution'))
            self.enableLeftSwitchCheckBox.setChecked(mot.get('leftswitchenable'))
            self.enableRightSwitchCheckBox.setChecked(mot.get('rightswitchenable'))
            self.freewheelingDelayDoubleSpinBox.setRange(0, 65.535)
            self.freewheelingDelayDoubleSpinBox.setSpecialValueText('Always on')
            self.freewheelingDelayDoubleSpinBox.setDecimals(3)
            self.freewheelingDelayDoubleSpinBox.setSingleStep(0.1)
            self.freewheelingDelayDoubleSpinBox.setValue(mot.get('freewheelingdelay'))
            self.maxSpeedSpinBox.setRange(0, 2047)
            self.maxAccelerationSpinBox.setRange(0, 2047)
            self.maxCurrentSpinBox.setRange(0, 255)
            self.standbyCurrentSpinBox.setRange(0, 255)
            self.setPhysRange()
        finally:
            # enable signals
            for widget in [self.pulseDivisorSpinBox, self.rampDivisorSpinBox, self.microstepResolutionSpinBox,
                           self.enableLeftSwitchCheckBox, self.enableRightSwitchCheckBox,
                           self.freewheelingDelayDoubleSpinBox, self.maxSpeedSpinBox, self.maxCurrentSpinBox,
                           self.maxAccelerationSpinBox, self.standbyCurrentSpinBox, self.maxSpeedDoubleSpinBox,
                           self.maxCurrentDoubleSpinBox, self.maxAccelerationDoubleSpinBox,
                           self.standbyCurrentDoubleSpinBox]:
                widget.blockSignals(False)
        self.maxSpeedSpinBox.setValue(mot.get('maxspeed:raw'))
        self.maxAccelerationSpinBox.setValue(mot.get('maxacceleration:raw'))
        self.maxCurrentSpinBox.setValue(mot.get('maxcurrent:raw'))
        self.standbyCurrentSpinBox.setValue(mot.get('standbycurrent:raw'))

    @Slot()
    def onRawPhysSpinboxChanged(self):
        motor = self.instrument.motors.get(self.motorSelectorComboBox.currentText())
        uc = UnitConverter(
            motor.unitConverter().top_rms_current, motor.unitConverter().fullstepsize, motor.unitConverter().clockfreq,
            self.pulseDivisorSpinBox.value(), self.rampDivisorSpinBox.value(), self.microstepResolutionSpinBox.value())

        for this, other, cvtfunc in [
            (self.maxSpeedSpinBox, self.maxSpeedDoubleSpinBox, uc.speed2phys),
            (self.maxAccelerationSpinBox, self.maxAccelerationDoubleSpinBox, uc.accel2phys),
            (self.maxCurrentSpinBox, self.maxCurrentDoubleSpinBox, uc.current2phys),
            (self.standbyCurrentSpinBox, self.standbyCurrentDoubleSpinBox, uc.current2phys),
            (self.maxSpeedDoubleSpinBox, self.maxSpeedSpinBox, uc.speed2raw),
            (self.maxAccelerationDoubleSpinBox, self.maxAccelerationSpinBox, uc.accel2raw),
            (self.maxCurrentDoubleSpinBox, self.maxCurrentSpinBox, uc.current2raw),
            (self.standbyCurrentDoubleSpinBox, self.standbyCurrentSpinBox, uc.current2raw),
        ]:
            if this is not self.sender():
                continue
            other.blockSignals(True)
            try:
                other.setValue(cvtfunc(this.value()))
            finally:
                other.blockSignals(False)

    @Slot()
    def recalculateRawToPhys(self):
        """Force the re-calculation of physical values from raw values by simulating valueChanged events for each raw
        spin-box."""
        for w in [self.maxCurrentDoubleSpinBox, self.standbyCurrentDoubleSpinBox, self.maxSpeedDoubleSpinBox, self.maxAccelerationDoubleSpinBox]:
            w.blockSignals(True)
        try:
            self.setPhysRange()
        finally:
            for w in [self.maxCurrentDoubleSpinBox, self.standbyCurrentDoubleSpinBox, self.maxSpeedDoubleSpinBox, self.maxAccelerationDoubleSpinBox]:
                w.blockSignals(False)
        self.maxCurrentSpinBox.valueChanged.emit(self.maxSpeedSpinBox.value())
        self.standbyCurrentSpinBox.valueChanged.emit(self.standbyCurrentSpinBox.value())
        self.maxSpeedSpinBox.valueChanged.emit(self.maxSpeedSpinBox.value())
        self.maxAccelerationSpinBox.valueChanged.emit(self.maxAccelerationSpinBox.value())

    def setMotor(self, motorname: str):
        self.motorSelectorComboBox.setCurrentIndex(self.motorSelectorComboBox.findText(motorname))

    def setPhysRange(self):
        """Update the range of physical value spin-boxes"""
        mot = self.instrument.motors.get(self.motorSelectorComboBox.currentText())
        uc = UnitConverter(
            mot.unitConverter().top_rms_current, mot.unitConverter().fullstepsize, mot.unitConverter().clockfreq,
        self.pulseDivisorSpinBox.value(), self.rampDivisorSpinBox.value(),
        self.microstepResolutionSpinBox.value())
        self.maxSpeedDoubleSpinBox.setRange(0, uc.maximumSpeed())
        self.maxAccelerationDoubleSpinBox.setRange(0, uc.maximumAcceleration())
        self.maxCurrentDoubleSpinBox.setRange(0, uc.maximumCurrent())
        self.standbyCurrentDoubleSpinBox.setRange(0, uc.maximumCurrent())
        self.maxSpeedDoubleSpinBox.setSingleStep(uc.speedStep())
        self.maxAccelerationDoubleSpinBox.setSingleStep(uc.accelerationStep())
        self.maxCurrentDoubleSpinBox.setSingleStep(uc.currentStep())
        self.standbyCurrentSpinBox.setSingleStep(uc.currentStep())
