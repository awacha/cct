from PySide6 import QtWidgets
from PySide6.QtCore import Slot

from .beamstopcalibrator_ui import Ui_Form
from ...utils.window import WindowRequiresDevices


class BeamStopCalibrator(WindowRequiresDevices, QtWidgets.QWidget, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.xInDoubleSpinBox.setValue(self.instrument.beamstop.inPosition()[0])
        self.yInDoubleSpinBox.setValue(self.instrument.beamstop.inPosition()[1])
        self.xOutDoubleSpinBox.setValue(self.instrument.beamstop.outPosition()[0])
        self.yOutDoubleSpinBox.setValue(self.instrument.beamstop.outPosition()[1])

    @Slot(bool)
    def on_fetchXInFromMotorToolButton_clicked(self, checked: bool):
        try:
            self.xInDoubleSpinBox.setValue(self.instrument.beamstop.motorx.where())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.window(), 'Cannot get X motor coordinate', exc.args[0])

    @Slot(bool)
    def on_fetchXOutFromMotorToolButton_clicked(self, checked: bool):
        try:
            self.xOutDoubleSpinBox.setValue(self.instrument.beamstop.motorx.where())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.window(), 'Cannot get X motor coordinate', exc.args[0])

    @Slot(bool)
    def on_fetchYInFromMotorToolButton_clicked(self, checked: bool):
        try:
            self.yInDoubleSpinBox.setValue(self.instrument.beamstop.motory.where())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.window(), 'Cannot get Y motor coordinate', exc.args[0])

    @Slot(bool)
    def on_fetchYOutFromMotorToolButton_clicked(self, checked: bool):
        try:
            self.yOutDoubleSpinBox.setValue(self.instrument.beamstop.motory.where())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.window(), 'Cannot get Y motor coordinate', exc.args[0])

    @Slot(bool)
    def on_resetXInToolButton_clicked(self, checked: bool):
        self.xInDoubleSpinBox.setValue(self.instrument.beamstop.inPosition()[0])

    @Slot(bool)
    def on_resetXOutToolButton_clicked(self, checked: bool):
        self.xOutDoubleSpinBox.setValue(self.instrument.beamstop.outPosition()[0])

    @Slot(bool)
    def on_resetYInToolButton_clicked(self, checked: bool):
        self.yInDoubleSpinBox.setValue(self.instrument.beamstop.inPosition()[1])

    @Slot(bool)
    def on_resetYOutToolButton_clicked(self, checked: bool):
        self.yOutDoubleSpinBox.setValue(self.instrument.beamstop.outPosition()[1])

    @Slot(bool)
    def on_saveInToolButton_clicked(self, checked: bool):
        self.savePosition("in")

    @Slot(bool)
    def on_saveOutToolButton_clicked(self, checked: bool):
        self.savePosition("out")

    def savePosition(self, inorout: str):
        if inorout == 'in':
            x = self.xInDoubleSpinBox.value()
            y = self.yInDoubleSpinBox.value()
        elif inorout == 'out':
            x = self.xOutDoubleSpinBox.value()
            y = self.yOutDoubleSpinBox.value()
        else:
            raise ValueError(inorout)
        if QtWidgets.QMessageBox.question(
                self.window(),
                'Confirm calibrating beam-stop position',
                f'Do you really want to set beam-stop {inorout} position '
                f'to ({x:.4f}, {y:.4f})?',
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No
        ) == QtWidgets.QMessageBox.StandardButton.No:
            QtWidgets.QMessageBox.information(
                self.window(),
                'Calibrating beam-stop position',
                f'Beam-stop {inorout} position NOT SET.')
            return
        try:
            if inorout == 'in':
                self.instrument.beamstop.calibrateIn(x, y)
            else:
                assert inorout == 'out'
                self.instrument.beamstop.calibrateOut(x, y)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self.window(), 'Calibrating beam-stop position',
                f'Error while calibrating beam-stop {inorout} position: '
                f'{exc.args[0]}.')
        else:
            if inorout == "in":
                newposition = self.instrument.beamstop.inPosition()
            else:
                assert inorout == "out"
                newposition = self.instrument.beamstop.outPosition()
            QtWidgets.QMessageBox.information(
                self.window(), 'Calibrating beam-stop position',
                f'Beam-stop in position successfully set to '
                f'{newposition}')
