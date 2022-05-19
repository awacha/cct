import logging
from typing import Optional

from PyQt5 import QtWidgets

from .motorconfig import AdvancedMotorConfig
from .addmotordialog import AddMotorDialog
from .autoadjust import AutoAdjustMotor
from .motorcalibration import MotorCalibrationDialog
from .motormover import MotorMover
from .motorview_ui import Ui_Form
from .samplemover import SampleMover
from ...utils.window import WindowRequiresDevices
from ...devices.beamstop import BeamstopIndicator
from .beamstopcalibrator import BeamStopCalibrator
from ....core2.instrument.components.auth.privilege import Privilege
from ....core2.devices import DeviceType
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MotorView(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    addMotorDialog: Optional[AddMotorDialog] = None
    motorCalibrationDialog: Optional[MotorCalibrationDialog] = None
    motorConfigurationDialog: Optional[AdvancedMotorConfig] = None
    connect_all_motors = True
    required_devicetypes = [DeviceType.MotorController]

    # component widgets
    motormover: MotorMover
    samplemover: SampleMover
    beamstop: BeamstopIndicator
    beamstopcalibrator: BeamStopCalibrator

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.motors)
        self.addMotorToolButton.clicked.connect(self.addMotor)
        self.removeMotorToolButton.clicked.connect(self.removeMotor)
        self.calibrateMotorToolButton.clicked.connect(self.calibrateMotor)
        self.autoAdjustMotorToolButton.clicked.connect(self.autoAdjustMotor)
        self.configureMotorToolButton.clicked.connect(self.configureMotor)
        self.motormover = MotorMover(parent=self.motorMoverGroupBox, mainwindow=self.mainwindow,
                                     instrument=self.instrument)
        self.motorMoverGroupBox.setLayout(QtWidgets.QVBoxLayout())
        self.motorMoverGroupBox.layout().addWidget(self.motormover)
        self.motormover.layout().setContentsMargins(0, 0, 0, 0)
        self.samplemover = SampleMover(parent=self.sampleMoverGroupBox, mainwindow=self.mainwindow,
                                       instrument=self.instrument)
        self.sampleMoverGroupBox.setLayout(QtWidgets.QVBoxLayout())
        self.sampleMoverGroupBox.layout().addWidget(self.samplemover)
        self.samplemover.layout().setContentsMargins(0, 0, 0, 0)
        self.beamstop = BeamstopIndicator(parent=self.beamStopMoverGroupBox, mainwindow=self.mainwindow,
                                          instrument=self.instrument)
        self.beamStopMoverGroupBox.setLayout(QtWidgets.QVBoxLayout())
        self.beamStopMoverGroupBox.layout().addWidget(self.beamstop)
        self.beamstop.layout().setContentsMargins(0, 0, 0, 0)
        self.beamstop.setFrameStyle(QtWidgets.QFrame.NoFrame)
        self.beamstopcalibrator = BeamStopCalibrator(parent=self.beamStopCalibratorGroupBox, mainwindow=self.mainwindow,
                                                     instrument=self.instrument)
        self.beamStopCalibratorGroupBox.setLayout(QtWidgets.QVBoxLayout())
        self.beamStopCalibratorGroupBox.layout().addWidget(self.beamstopcalibrator)
        self.beamstopcalibrator.layout().setContentsMargins(0,0,0,0)

    def addMotor(self):
        if not self.instrument.auth.hasPrivilege(Privilege.MotorConfiguration):
            QtWidgets.QMessageBox.critical(self, 'Insufficient privileges', 'Insufficient privileges to add a motor.')
            return
        self.addMotorDialog = AddMotorDialog(parent=self)
        self.addMotorDialog.finished.connect(self.onAddMotorDialogFinished)
        self.addMotorDialog.show()

    def onAddMotorDialogFinished(self, accepted: bool):
        if accepted:
            self.instrument.motors.addMotor(
                self.addMotorDialog.motorName(),
                self.addMotorDialog.controllerName(),
                self.addMotorDialog.axis(),
                self.addMotorDialog.leftlimit(),
                self.addMotorDialog.rightlimit(),
                self.addMotorDialog.position(),
                self.addMotorDialog.motorrole(),
                self.addMotorDialog.motordirection(),
            )
        self.addMotorDialog.finished.disconnect(self.onAddMotorDialogFinished)
        self.addMotorDialog.close()
        self.addMotorDialog.deleteLater()
        self.addMotorDialog = None

    def removeMotor(self):
        index = self.treeView.selectionModel().currentIndex()
        if not index.isValid():
            return
        if not self.instrument.auth.hasPrivilege(Privilege.MotorConfiguration):
            QtWidgets.QMessageBox.critical(self, 'Insufficient privileges',
                                           'Cannot remove motor: not enough privileges.')
            return
        self.instrument.motors.removeMotor(self.instrument.motors[index.row()].name)

    def configureMotor(self):
        if not self.instrument.auth.hasPrivilege(Privilege.MotorConfiguration):
            QtWidgets.QMessageBox.critical(
                self, "Insufficient privileges", 'Cannot configure motor: insufficient privileges')
            return
        if not self.treeView.selectionModel().currentIndex().isValid():
            return
        win = self.mainwindow.addSubWindow(AdvancedMotorConfig, singleton=False)
        if win is None:
            return
        win.setMotor(self.instrument.motors[self.treeView.selectionModel().currentIndex().row()].name)


    def calibrateMotor(self):
        if not self.instrument.auth.hasPrivilege(Privilege.MotorCalibration):
            QtWidgets.QMessageBox.critical(
                self, "Insufficient privileges", "Cannot calibrate motor: insufficient privileges")
            return
        if self.motorCalibrationDialog is None:
            self.motorCalibrationDialog = MotorCalibrationDialog(
                parent=self,
                motorname=self.instrument.motors[self.treeView.selectionModel().currentIndex().row()].name)
            self.motorCalibrationDialog.finished.connect(self.onMotorCalibrationDialogFinished)
            self.motorCalibrationDialog.show()
        else:
            self.motorCalibrationDialog.show()
            self.motorCalibrationDialog.raise_()
            self.motorCalibrationDialog.setFocus()

    def onMotorCalibrationDialogFinished(self, accepted: bool):
        if accepted:
            motor = self.instrument.motors[self.motorCalibrationDialog.motorname]
            motor.setLimits(self.motorCalibrationDialog.leftLimit(), self.motorCalibrationDialog.rightLimit())
            motor.setPosition(self.motorCalibrationDialog.position())
        self.motorCalibrationDialog.close()
        self.motorCalibrationDialog.deleteLater()
        self.motorCalibrationDialog = None

    def autoAdjustMotor(self):
        if not self.treeView.selectionModel().currentIndex().isValid():
            return
        if not self.instrument.auth.hasPrivilege(Privilege.MotorCalibration):
            QtWidgets.QMessageBox.critical(self, 'Insufficient privileges to calibrate motors.')
            return
        win = self.mainwindow.addSubWindow(AutoAdjustMotor, singleton=False)
        if win is None:
            return
        win.setMotor(self.instrument.motors[self.treeView.selectionModel().currentIndex().row()].name)

    def onCommandResult(self, name: str, success: str, message: str):
        pass
