from PyQt5 import QtWidgets, QtCore, QtGui

from .motorlist import MotorModel
from .motorview_ui import Ui_Form
from ..motorconfig import MotorConfig
from ..movemotor import MoveMotor
from ....core.mixins import ToolWindow
from .....core.devices import DeviceError
from .....core.devices.motor import Motor
from .....core.instrument.instrument import Instrument
from .....core.services.samples import SampleStore, Sample


class MotorOverview(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, parent, credo):
        QtWidgets.QWidget.__init__(self, parent)
        assert isinstance(credo, Instrument)
        ToolWindow.__init__(self, credo, required_devices=['Motor_' + m for m in credo.motors])
        self._updating_ui = False
        self._current_task = None
        self._samplestore_connections = []
        self._popupmenu = None
        self._calibrationwindows = {}
        self.setupUi(self)

    @classmethod
    def testRequirements(cls, credo:Instrument):
        if not super().testRequirements(credo):
            return False
        for m in credo.motors:
            if not credo.motors[m].controller.ready:
                return False
        for motor in ['Sample_X', 'Sample_Y', 'PH1_X', 'PH1_Y', 'PH2_X', 'PH2_Y', 'PH3_X', 'PH3_Y', 'BeamStop_X', 'BeamStop_Y']:
            if motor not in credo.motors:
                return False
        return True

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.motorModel = MotorModel(credo=self.credo)
        self.treeView.setModel(self.motorModel)
        self.movetoSamplePushButton.clicked.connect(self.onMoveToSample)
        self.movetoSampleXPushButton.clicked.connect(self.onMoveToSampleX)
        self.movetoSampleYPushButton.clicked.connect(self.onMoveToSampleY)
        self.beamstopControlComboBox.currentTextChanged.connect(self.onBeamStopMovementRequest)
        self.calibrateBeamstopPushButton.clicked.connect(self.onCalibrate)
        self.motorNameComboBox.currentIndexChanged.connect(self.onMotorNameChosen)
        self.relativeMovementCheckBox.toggled.connect(self.onRelativeChecked)
        self.moveMotorPushButton.clicked.connect(self.onMoveMotorClicked)
        self.motorNameComboBox.addItems(sorted(self.credo.motors))
        ss = self.credo.services['samplestore']
        assert isinstance(ss, SampleStore)
        self._samplestore_connections = [ss.connect('list-changed', self.onSampleListChanged)]
        self.onSampleListChanged()
        self.treeView.activated.connect(self.onMotorViewLineActivated)
        self.treeView.customContextMenuRequested.connect(self.onTreeViewContextMenuRequested)

    def onTreeViewContextMenuRequested(self, pos:QtCore.QPoint):
        if self._popupmenu is not None:
            try:
                self._popupmenu.close()
            except RuntimeError:
                pass
            self._popupmenu = None
            self._motor_for_popupmenu=None
        index = self.treeView.indexAt(pos)
        print(index)
        motor = self.credo.motors[sorted(self.credo.motors.keys())[index.row()]]
        assert isinstance(motor, Motor)
        self._popupmenu = QtWidgets.QMenu('Operations with motor {}'.format(motor.name))
        self._motor_for_popupmenu=motor
        if MoveMotor.testRequirements(self.credo):
            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(":/icons/motor.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self._popupmenu.addAction(icon, 'Move {}'.format(motor.name), self.onMoveMotorRequestedFromContextMenu)
        if MotorConfig.testRequirements(self.credo):
            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(":/icons/editconfig.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self._popupmenu.addAction(icon, 'Configure {}'.format(motor.name), self.onConfigureMotorRequestedFromContextMenu)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/calibration.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self._popupmenu.addAction(icon, 'Calibrate {}'.format(motor.name), self.onCalibrateMotorRequestedFromContextMenu)
        self._popupmenu.popup(QtGui.QCursor.pos())

    def onCalibrateMotorRequestedFromContextMenu(self):
        pass

    def onMoveMotorRequestedFromContextMenu(self):
        mm = MoveMotor(credo=self.credo, motorname=self._motor_for_popupmenu.name)
        mm.show()

    def onConfigureMotorRequestedFromContextMenu(self):
        try:
            self._calibrationwindows[self._motor_for_popupmenu.name].raise_()
        except (RuntimeError, KeyError):
            self._calibrationwindows[self._motor_for_popupmenu.name] = MotorConfig(None, motor=self._motor_for_popupmenu, credo=self.credo)
            self._calibrationwindows[self._motor_for_popupmenu.name].show()
            self._calibrationwindows[self._motor_for_popupmenu.name].raise_()

    def onMotorViewLineActivated(self, index:QtCore.QModelIndex):
        motor = self.credo.motors[sorted(self.credo.motors.keys())[index.row()]]
        self.motorNameComboBox.setCurrentIndex(self.motorNameComboBox.findText(motor.name))

    def cleanup(self):
        for c in self._samplestore_connections:
            self.credo.services['samplestore'].disconnect(c)
        self._samplestore_connections = []
        return super().cleanup()

    def onSampleListChanged(self):
        self._updating_ui = True
        lastsample = self.sampleNameComboBox.currentText()
        try:
            ss = self.credo.services['samplestore']
            assert isinstance(ss, SampleStore)
            self.sampleNameComboBox.clear()
            self.sampleNameComboBox.addItems(sorted([s.title for s in ss.get_samples()]))
            self.sampleNameComboBox.setCurrentIndex(self.sampleNameComboBox.findText(lastsample))
        finally:
            self._updating_ui = False

    def onMoveToSample(self):
        self._current_task = 'movetosample'
        self.onMoveToSampleX()

    def onMoveToSampleX(self):
        if self._current_task is None:
            self._current_task = 'movetosamplex'
        motor = self.credo.motors['Sample_X']
        assert isinstance(motor, Motor)
        ss = self.credo.services['samplestore']
        assert isinstance(ss, SampleStore)
        sample = ss.get_sample(self.sampleNameComboBox.currentText())
        assert isinstance(ss, Sample)
        try:
            motor.moveto(sample.positionx.val)
        except DeviceError as exc:
            QtWidgets.QMessageBox.critical(
                self, 'Sample positioning error',
                'Error starting movement of motor {} to {}: {}'.format(
                    motor.name, sample.positionx.val, exc.args[0]))
            self._current_task = None

    def onMoveToSampleY(self):
        if self._current_task is None:
            self._current_task = 'movetosampley'
        motor = self.credo.motors['Sample_Y']
        assert isinstance(motor, Motor)
        ss = self.credo.services['samplestore']
        assert isinstance(ss, SampleStore)
        sample = ss.get_sample(self.sampleNameComboBox.currentText())
        assert isinstance(ss, Sample)
        try:
            motor.moveto(sample.positiony.val)
        except DeviceError as exc:
            QtWidgets.QMessageBox.critical(
                self, 'Sample positioning error',
                'Error starting movement of motor {} to {}: {}'.format(
                    motor.name, sample.positiony.val, exc.args[0]))
            self._current_task = None

    def onBeamStopMovementRequest(self):
        if self._updating_ui:
            return
        if self.beamstopControlComboBox.currentIndex() == 0:
            target = self.credo.config['beamstop']['in'][0]
            self._current_task = 'beamstop_in'
        else:
            target = self.credo.config['beamstop']['out'][0]
            self._current_task = 'beamstop_out'
        assert isinstance(self.credo, Instrument)
        motor = self.credo.motors['BeamStop_X']
        try:
            motor.moveto(target)
        except DeviceError as exc:
            QtWidgets.QMessageBox.critical(
                self, 'Beamstop error',
                'Error starting movement of motor {} to {}: {}'.format(
                    motor.name, target, exc.args[0]))
            self._current_task = None

    def onCalibrate(self):
        if self.beamstopCalibrationTargetComboBox.currentText() == 'In':
            what = 'in'
        else:
            what = 'out'
        if QtWidgets.QMessageBox.question(
                self, 'Confirm calibration',
                'Do you want to calibrate the current beamstop position ({:.4f}, {:.4f}) as the new {} position?'.format(
                    self.credo.motors['BeamStop_X'].where(), self.credo.motors['BeamStop_Y'].where(), what),
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No) in [QtWidgets.QMessageBox.Yes]:
            self.credo.config['beamstop'][what] = (self.credo.motors['BeamStop_X'].where(), self.credo.motors['BeamStop_Y'].where())
            self.credo.save_state()

    def onMotorNameChosen(self):
        assert isinstance(self.credo, Instrument)
        motorname = self.motorNameComboBox.currentText()
        motor = self.credo.motors[motorname]
        assert isinstance(motor, Motor)
        if self.relativeMovementCheckBox.isChecked():
            self.motorTargetDoubleSpinBox.setMinimum(motor.get_variable('softleft') - motor.where())
            self.motorTargetDoubleSpinBox.setMaximum(motor.get_variable('softright') - motor.where())
            self.motorTargetDoubleSpinBox.setValue(0)
        else:
            self.motorTargetDoubleSpinBox.setMinimum(motor.get_variable('softleft'))
            self.motorTargetDoubleSpinBox.setMaximum(motor.get_variable('softright'))
            self.motorTargetDoubleSpinBox.setValue(motor.where())

    def onRelativeChecked(self):
        return self.onMotorNameChosen()

    def onMoveMotorClicked(self):
        motor = self.credo.motors[self.motorNameComboBox.currentText()]
        assert isinstance(motor, Motor)
        try:
            if self.relativeMovementCheckBox.isChecked():
                motor.moverel(self.motorTargetDoubleSpinBox.value())
            else:
                motor.moveto(self.motorTargetDoubleSpinBox.value())
        except DeviceError as exc:
            QtWidgets.QMessageBox.critical(self, 'Error moving motor',
                                           'Error starting movement of motor {} to {}: {}'.format(
                                               motor.name, self.motorTargetDoubleSpinBox.value(), exc.args[0]))

    def onMotorStart(self, motor: Motor):
        self.highLevelGroupBox.setEnabled(False)
        self.moveMotorGroupBox.setEnabled(False)
        if motor.name in ['BeamStop_X', 'BeamStop_Y']:
            self.updateBeamstopIndicator()

    def onMotorStop(self, motor: Motor, targetpositionreached: bool):
        self.highLevelGroupBox.setEnabled(True)
        self.moveMotorGroupBox.setEnabled(True)
        self.onMotorNameChosen()
        self.updateBeamstopIndicator()
        if self._current_task is None:
            pass
        elif self._current_task == 'movetosample' and motor.name == 'Sample_X':
            self.onMoveToSampleY()
        elif self._current_task.startswith('beamstop_') and motor.name == 'BeamStop_X':
            if self._current_task.endswith('_in'):
                target = self.credo.config['beamstop']['in'][1]
            else:
                target = self.credo.config['beamstop']['out'][1]
            assert isinstance(self.credo, Instrument)
            motor = self.credo.motors['BeamStop_Y']
            try:
                motor.moveto(target)
            except DeviceError as exc:
                QtWidgets.QMessageBox.critical(
                    self, 'Beamstop error',
                    'Error starting movement of motor {} to {}: {}'.format(
                        motor.name, target, exc.args[0]))
                self._current_task = None
        else:
            self._current_task = None

    def updateBeamstopIndicator(self):
        self._updating_ui = True
        try:
            assert isinstance(self.credo, Instrument)
            if self.credo.get_beamstop_state() == 'in':
                self.beamstopControlComboBox.setCurrentIndex(0)
            elif self.credo.get_beamstop_state() == 'out':
                self.beamstopControlComboBox.setCurrentIndex(1)
            else:
                self.beamstopControlComboBox.setCurrentIndex(-1)
        finally:
            self._updating_ui = False

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        pass
