import logging

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
from ....core.utils.inhibitor import Inhibitor

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
        self._origin = None
        self._stepsize = None
        self._updating_stepsize=Inhibitor()
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        assert isinstance(self.credo, Instrument)
        self.motorComboBox.addItems(sorted(self.credo.motors.keys()))
        self.motorComboBox.setCurrentIndex(0)
        self.motorComboBox.currentTextChanged.connect(self.onMotorSelected)
        self.scanTypeComboBox.currentTextChanged.connect(self.onScanTypeSelected)
        self.startDoubleSpinBox.valueChanged.connect(self.recalculateStepSize)
        self.endDoubleSpinBox.valueChanged.connect(self.recalculateStepSize)
        self.stepSizeDoubleSpinBox.valueChanged.connect(self.onStepSizeChanged)
        self.stepsSpinBox.valueChanged.connect(self.recalculateStepSize)
        self.progressBar.setVisible(False)
        self.startStopPushButton.clicked.connect(self.onStartStop)
        self.adjustSize()
        self.onMotorSelected()

    def onStepSizeChanged(self):
        if self._updating_stepsize.inhibited:
            return
        with self._updating_stepsize:
            # try to find the best #steps
            if self.scanTypeComboBox.currentText() in ['Absolute', 'Relative']:
                span = self.endDoubleSpinBox.value()-self.startDoubleSpinBox.value()
            elif self.scanTypeComboBox.currentText() in ['Symmetric relative']:
                span = 2*self.startDoubleSpinBox.value()
            else:
                raise ValueError(self.scanTypeComboBox.currentText())
            nsteps=round(abs(span)/self.stepSizeDoubleSpinBox.value())
            if nsteps<self.stepsSpinBox.minimum() or  nsteps>self.stepsSpinBox.maximum():
                pass
            else:
                self.stepsSpinBox.setValue(nsteps)
        self.recalculateStepSize()

    def onScanTypeSelected(self, scantype):
        self.updateSpinBoxes()

    def onMotorSelected(self):
        if self._motor is not None:
            self.unrequireDevice('Motor_' + self._motor)
            self._motor = None
        self._motor = self.motorComboBox.currentText()
        self.requireDevice('Motor_' + self._motor)
        self.updateSpinBoxes()

    def updateSpinBoxes(self, where=None):
        motor = self.credo.motors[self._motor]
        assert isinstance(motor, Motor)
        if self.scanTypeComboBox.currentText()=='Relative':
            if where is None:
                where = motor.where()
            self.startDoubleSpinBox.setMinimum(motor.get_variable('softleft') - where)
            self.startDoubleSpinBox.setMaximum(motor.get_variable('softright') - where)
            self.endDoubleSpinBox.setMinimum(motor.get_variable('softleft') - where)
            self.endDoubleSpinBox.setMaximum(motor.get_variable('softright') - where)
            self.leftLimitLabel.setText('{:.4f}'.format(motor.get_variable('softleft') -where))
            self.rightLimitLabel.setText('{:.4f}'.format(motor.get_variable('softright') -where))
            self.endLabel.setVisible(True)
            self.startLabel.setText('Start:')
            self.endDoubleSpinBox.setVisible(True)
        elif self.scanTypeComboBox.currentText()=='Absolute':
            self.startDoubleSpinBox.setMinimum(motor.get_variable('softleft'))
            self.startDoubleSpinBox.setMaximum(motor.get_variable('softright'))
            self.endDoubleSpinBox.setMinimum(motor.get_variable('softleft'))
            self.endDoubleSpinBox.setMaximum(motor.get_variable('softright'))
            self.leftLimitLabel.setText('{:.4f}'.format(motor.get_variable('softleft')))
            self.rightLimitLabel.setText('{:.4f}'.format(motor.get_variable('softright')))
            self.endLabel.setVisible(True)
            self.startLabel.setText('Start:')
            self.endDoubleSpinBox.setVisible(True)
        elif self.scanTypeComboBox.currentText()=='Symmetric relative':
            if where is None:
                where = motor.where()
            self.startDoubleSpinBox.setMinimum(0)
            maxhwhm=min(where-motor.get_variable('softleft'), motor.get_variable('softright')-where)
            self.leftLimitLabel.setText('{:.4f}'.format(-maxhwhm))
            self.rightLimitLabel.setText('{:.4f}'.format(maxhwhm))
            self.startDoubleSpinBox.setMaximum(maxhwhm)
            self.startLabel.setText('Half width:')
            self.endLabel.setVisible(False)
            self.endDoubleSpinBox.setVisible(False)
        else:
            raise ValueError(self.scanTypeComboBox.currentText())
        self.adjustSize()

    def recalculateStepSize(self):
        if self.scanTypeComboBox.currentText()=='Symmetric relative':
            stepsize = self.startDoubleSpinBox.value()*2/(self.stepsSpinBox.value()-1)
        else:
            stepsize = (self.endDoubleSpinBox.value() - self.startDoubleSpinBox.value()) / (self.stepsSpinBox.value() - 1)
        if not self._updating_stepsize.inhibited:
            with self._updating_stepsize:
                self.stepSizeDoubleSpinBox.setValue(abs(stepsize))

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        if not self.isBusy() and self.scanTypeComboBox.currentText() in ['Relative', 'Symmetric relative']:
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
        logger.debug('onCmdReturn(interpreter, {}, {})'.format(cmdname, retval))
        if cmdname == 'moveto':
            if self._failed or self._origin is None:
                logger.debug('Setting UI to idle after moveto')
                self.setIdle()
            elif self.autoShutterCheckBox.isChecked():
                logger.debug('Opening shutter after moveto')
                self.executeCommand(Shutter, True)
            else:
                logger.debug('Simulating opening shutter after moveto')
                self.onCmdReturn(self.credo.services['interpreter'], 'shutter', True)
        elif cmdname == 'scan':
            if self.autoShutterCheckBox.isChecked():
                logger.debug('Closing shutter after scan')
                self.executeCommand(Shutter, False)
            else:
                logger.debug('Simulating closing shutter after scan')
                self.onCmdReturn(self.credo.services['interpreter'], 'shutter', False)
        elif cmdname == 'shutter' and retval:
            if self._failed:
                self.setIdle()
            else:
                logger.debug('Shutter is open, starting scan.')
                # shutter is open, start scan.
                motor = self.credo.motors[self._motor]
                assert isinstance(motor, Motor)
                if self.scanTypeComboBox.currentText()=='Relative':
                    start = motor.where()
                    end = motor.where() + self.endDoubleSpinBox.value() - self.startDoubleSpinBox.value()
                elif self.scanTypeComboBox.currentText()=='Absolute':
                    start = self.startDoubleSpinBox.value()
                    end = self.endDoubleSpinBox.value()
                elif self.scanTypeComboBox.currentText()=='Symmetric relative':
                    start = motor.where()
                    end=motor.where() + 2*self.startDoubleSpinBox.value()
                else:
                    raise ValueError(self.scanTypeComboBox.currentText())
                self._scangraph = ScanGraph(credo=self.credo)
                self._scangraph.setWindowTitle('Scan #{:d}'.format(self.credo.services['filesequence'].get_nextfreescan(acquire=False)))
                self._scangraph.setCurve([self._motor] + self.credo.config['scan']['columns'],
                                         self.stepsSpinBox.value())
                self._scangraph.show()
                self.executeCommand(Scan, self.motorComboBox.currentText(), start,
                                    end, self.stepsSpinBox.value(),
                                    self.countingTimeDoubleSpinBox.value(), self.commentLineEdit.text())
        elif cmdname == 'shutter' and not retval:
            if self.goBackAfterEndCheckBox.isChecked():
                logger.debug('Going back to the start')
                self.executeCommand(Moveto, self._motor, self._origin)
                self._origin = None
            else:
                logger.debug('Simulating going back to the start')
                self._origin = None
                self.onCmdReturn(interpreter, 'moveto', True)

    def onCmdDetail(self, interpreter: Interpreter, cmdname: str, detail):
        fsn, position, counters = detail
        assert isinstance(self._scangraph, ScanGraph)
        self._scangraph.appendScanPoint(tuple(counters))

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
                if self.scanTypeComboBox.currentText()=='Relative':
                    start = self.startDoubleSpinBox.value() + motor.where()
                elif self.scanTypeComboBox.currentText()=='Absolute':
                    start = self.startDoubleSpinBox.value()
                elif self.scanTypeComboBox.currentText()=='Symmetric relative':
                    start = motor.where() - self.startDoubleSpinBox.value()
                else:
                    raise ValueError(self.scanTypeComboBox.currentText())
                self.executeCommand(Moveto, self._motor, start)
            except Exception as exc:
                self.setIdle()
                QtWidgets.QMessageBox.critical(self, 'Error while start scan', exc.args[0])
        else:
            self.credo.services['interpreter'].kill()
