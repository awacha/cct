from PySide6 import QtWidgets
from PySide6.QtCore import Slot

from .beamstopcalibrator_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.auth.privilege import Privilege


class BeamStopCalibrator(WindowRequiresDevices, QtWidgets.QWidget, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.calibrateBeamStopPushButton.clicked.connect(self.calibrateBeamStopPosition)
        self.inRadioButton.toggled.connect(self.inOutChanged)
        self.fetchXFromMotorToolButton.clicked.connect(self.fetchXFromMotor)
        self.fetchYFromMotorToolButton.clicked.connect(self.fetchYFromMotor)
        self.resetXToolButton.clicked.connect(self.loadX)
        self.resetYToolButton.clicked.connect(self.loadY)

    @Slot(bool)
    def inOutChanged(self, isin: bool):
        self.loadX()
        self.loadY()

    @Slot()
    def fetchXFromMotor(self):
        try:
            self.xDoubleSpinBox.setValue(self.instrument.beamstop.motorx.where())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.window(), 'Cannot get X motor coordinate', exc.args[0])

    @Slot()
    def fetchYFromMotor(self):
        try:
            self.yDoubleSpinBox.setValue(self.instrument.beamstop.motory.where())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.window(), 'Cannot get Y motor coordinate', exc.args[0])

    @Slot()
    def loadX(self):
        self.xDoubleSpinBox.setValue(self.instrument.beamstop.inPosition()[0] if self.inRadioButton.isChecked() else
                                     self.instrument.beamstop.outPosition()[0])

    @Slot()
    def loadY(self):
        self.yDoubleSpinBox.setValue(self.instrument.beamstop.inPosition()[1] if self.inRadioButton.isChecked() else
                                     self.instrument.beamstop.outPosition()[1])

    @Slot()
    def calibrateBeamStopPosition(self):
        if QtWidgets.QMessageBox.question(
                self.window(),
                'Confirm calibrating beam-stop position',
                f'Do you really want to set beam-stop {"in" if self.inRadioButton.isChecked() else "out"} position '
                f'to ({self.xDoubleSpinBox.value():.4f}, {self.yDoubleSpinBox.value():.4f})?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
        ) == QtWidgets.QMessageBox.No:
            QtWidgets.QMessageBox.information(
                self.window(),
                'Calibrating beam-stop position',
                f'Beam-stop {"in" if self.inRadioButton.isChecked() else "out"} position NOT SET.')
            return
        try:
            if self.inRadioButton.isChecked():
                self.instrument.beamstop.calibrateIn(self.xDoubleSpinBox.value(), self.yDoubleSpinBox.value())
            else:
                self.instrument.beamstop.calibrateOut(self.xDoubleSpinBox.value(), self.yDoubleSpinBox.value())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self.window(), 'Calibrating beam-stop position',
                f'Error while calibrating beam-stop {"in" if self.inRadioButton.isChecked() else "out"} position: '
                f'{exc.args[0]}.')
        else:
            QtWidgets.QMessageBox.information(
                self.window(), 'Calibrating beam-stop position',
                f'Beam-stop {"in" if self.inRadioButton.isChecked() else "out"} position successfully set to '
                f'{self.instrument.beamstop.inPosition() if self.inRadioButton.isChecked() else self.instrument.beamstop.outPosition()}')
