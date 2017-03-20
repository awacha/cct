from PyQt5 import QtWidgets

from .scan_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.devices import Motor
from ....core.instrument.instrument import Instrument


class ScanMeasurement(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['pilatus', 'genix']
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo)
        self._motor = None
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        assert isinstance(self.credo, Instrument)
        self.motorComboBox.addItems(sorted(self.credo.motors.keys()))
        self.motorComboBox.setCurrentIndex(0)
        self.motorComboBox.currentTextChanged.connect(self.onMotorSelected)
        self.startDoubleSpinBox.valueChanged.connect(self.recalculateStepSize)
        self.endDoubleSpinBox.valueChanged.connect(self.recalculateStepSize)
        self.stepsSpinBox.valueChanged.connect(self.recalculateStepSize)
        self.progressBar.setVisible(False)

    def onMotorSelected(self):
        if self._motor is not None:
            self.unrequireDevice(self._motor)
            self._motor = None
        self._motor = self.motorComboBox.currentText()
        self.requireDevice('Motor_'+self._motor)
        self.updateSpinBoxes()

    def updateSpinBoxes(self, where=None):
        motor = self.credo.motors[self._motor]
        assert isinstance(motor, Motor)
        if self.relativeScanCheckBox.isChecked():
            if where is None:
                where = motor.where()
            self.startDoubleSpinBox.setMinimum(motor.get_variable('softleft')-where)
            self.startDoubleSpinBox.setMaximum(motor.get_variable('softright')-where)
            self.endDoubleSpinBox.setMinimum(motor.get_variable('softleft')-where)
            self.endDoubleSpinBox.setMaximum(motor.get_variable('softright')-where)
        else:
            self.startDoubleSpinBox.setMinimum(motor.get_variable('softleft'))
            self.startDoubleSpinBox.setMaximum(motor.get_variable('softright'))
            self.endDoubleSpinBox.setMinimum(motor.get_variable('softleft'))
            self.endDoubleSpinBox.setMaximum(motor.get_variable('softright'))

    def recalculateStepSize(self):
        self.stepSizeLabel.setText('{:.4f}'.format(
            self.endDoubleSpinBox.value()-self.startDoubleSpinBox.value()/(self.stepsSpinBox.value()-1)))

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        if not self.isBusy() and self.relativeScanCheckBox.isChecked():
            self.updateSpinBoxes()

    def setBusy(self):
        super().setBusy()
        self.inputForm.setEnabled(False)

    def setIdle(self):
        super().setIdle()
        self.inputForm.setEnabled(True)
