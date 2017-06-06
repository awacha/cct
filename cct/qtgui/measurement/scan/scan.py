from PyQt5 import QtWidgets, QtGui

from .scan_ui import Ui_Form
from ...core.mixins import ToolWindow
from ...core.scangraph import ScanGraph
from ....core.commands.motor import Moveto
from ....core.commands.scan import Scan
from ....core.commands.xray_source import Shutter
from ....core.devices import Motor
from ....core.instrument.instrument import Instrument
from ....core.instrument.privileges import PRIV_MOVEMOTORS
from ....core.services.interpreter import Interpreter


class ScanMeasurement(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['pilatus', 'genix']
    required_privilege = PRIV_MOVEMOTORS

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self._motor = None
        self._scangraph = None
        self._failed = False
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
        self.startStopPushButton.clicked.connect(self.onStartStop)

    def onMotorSelected(self):
        if self._motor is not None:
            self.unrequireDevice(self._motor)
            self._motor = None
        self._motor = self.motorComboBox.currentText()
        self.requireDevice('Motor_' + self._motor)
        self.updateSpinBoxes()

    def updateSpinBoxes(self, where=None):
        motor = self.credo.motors[self._motor]
        assert isinstance(motor, Motor)
        if self.relativeScanCheckBox.isChecked():
            if where is None:
                where = motor.where()
            self.startDoubleSpinBox.setMinimum(motor.get_variable('softleft') - where)
            self.startDoubleSpinBox.setMaximum(motor.get_variable('softright') - where)
            self.endDoubleSpinBox.setMinimum(motor.get_variable('softleft') - where)
            self.endDoubleSpinBox.setMaximum(motor.get_variable('softright') - where)
        else:
            self.startDoubleSpinBox.setMinimum(motor.get_variable('softleft'))
            self.startDoubleSpinBox.setMaximum(motor.get_variable('softright'))
            self.endDoubleSpinBox.setMinimum(motor.get_variable('softleft'))
            self.endDoubleSpinBox.setMaximum(motor.get_variable('softright'))

    def recalculateStepSize(self):
        self.stepSizeLabel.setText('{:.4f}'.format(
            self.endDoubleSpinBox.value() - self.startDoubleSpinBox.value() / (self.stepsSpinBox.value() - 1)))

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        if not self.isBusy() and self.relativeScanCheckBox.isChecked():
            self.updateSpinBoxes()

    def setBusy(self):
        super().setBusy()
        self.inputForm.setEnabled(False)
        self.startStopPushButton.setText('Stop')
        self.startStopPushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))

    def setIdle(self):
        super().setIdle()
        self.inputForm.setEnabled(True)
        self.startStopPushButton.setText('Start')
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/scan.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.startStopPushButton.setIcon(icon)
        self._scangraph = None

    def onCmdFail(self, interpreter: Interpreter, cmdname: str, exception: Exception, traceback: str):
        self._failed = True

    def onCmdReturn(self, interpreter: Interpreter, cmdname: str, retval):
        super().onCmdReturn(interpreter, cmdname, retval)
        if cmdname == 'moveto':
            if self._failed:
                self.setIdle()
            if self._origin is None:
                self.setIdle()
            elif self.autoShutterCheckBox.isChecked():
                self.executeCommand(Shutter, True)
            else:
                self.onCmdReturn(self.credo.services['interpreter'], 'shutter', True)
        elif cmdname == 'scan':
            if self.autoShutterCheckBox.isChecked():
                self.executeCommand(Shutter, False)
            else:
                self.setIdle()
        elif cmdname == 'shutter' and retval:
            if self._failed:
                self.setIdle()
            else:
                # shutter is open, start scan.
                motor = self.credo.motors[self._motor]
                assert isinstance(motor, Motor)
                if self.relativeScanCheckBox.isChecked():
                    start = motor.where()
                    end = motor.where() + self.endDoubleSpinBox.value() - self.startDoubleSpinBox.value()
                else:
                    start = self.startDoubleSpinBox.value()
                    end = self.endDoubleSpinBox.value()
                self._scangraph = ScanGraph(credo=self.credo)
                self._scangraph.setCurve([self._motor] + self.credo.config['scan']['columns'],
                                         self.stepsSpinBox.value())
                self._scangraph.show()
                self.executeCommand(Scan, self.motorComboBox.currentText(), start,
                                    end, self.stepsSpinBox.value(),
                                    self.countingTimeDoubleSpinBox.value(), self.commentLineEdit.text())
        elif cmdname == 'shutter' and not retval:
            if self.goBackAfterEndCheckBox.isChecked():
                self.executeCommand(Moveto, self._motor, self._origin)
            else:
                self.onCmdReturn(interpreter, 'moveto', True)
            self._origin = None

    def onCmdDetail(self, interpreter: Interpreter, cmdname: str, detail):
        fsn, position, counters = detail
        assert isinstance(self._scangraph, ScanGraph)
        self._scangraph.appendScanPoint((position,) + tuple(counters))

    def onStartStop(self):
        if self.startStopPushButton.text() == 'Start':
            if not self.commentLineEdit.text().strip():
                QtWidgets.QMessageBox.critical(self, 'Cannot start scan',
                                               'Please describe the scan measurement in the "comment" field!')
                return
            self.setBusy()
            self._failed = False
            try:
                motor = self.credo.motors[self._motor]
                assert isinstance(motor, Motor)
                self._origin = motor.where()
                if self.relativeScanCheckBox.isChecked():
                    start = self.startDoubleSpinBox.value() + motor.where()
                else:
                    start = self.startDoubleSpinBox.value()
                self.executeCommand(Moveto, self._motor, start)
            except Exception as exc:
                self.setIdle()
                QtWidgets.QMessageBox.critical(self, 'Error while start scan', exc.args[0])
        else:
            self.credo.services['interpreter'].kill()
