from PyQt5 import QtWidgets

from .motorcalibration_ui import Ui_Form
from ....core.mixins import ToolWindow
from .....core.devices import Motor
from .....core.instrument.privileges import PRIV_MOTORCALIB


class MotorCalibration(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_privilege = PRIV_MOTORCALIB

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        self.motorname = kwargs.pop('motorname')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo=credo, required_devices=['Motor_' + self.motorname])
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, self)
        motor = self.credo.motors[self.motorname]
        assert isinstance(motor, Motor)
        self.calibratePushButton.clicked.connect(self.onCalibrate)
        self.leftLimitDoubleSpinBox.valueChanged.connect(self.onRelim)
        self.rightLimitDoubleSpinBox.valueChanged.connect(self.onRelim)
        self.leftLimitDoubleSpinBox.setMinimum(-1e6)
        self.leftLimitDoubleSpinBox.setMaximum(1e6)
        self.rightLimitDoubleSpinBox.setMaximum(1e6)
        self.rightLimitDoubleSpinBox.setMinimum(-1e6)
        self.leftLimitDoubleSpinBox.setValue(motor.get_variable('softleft'))
        self.rightLimitDoubleSpinBox.setValue(motor.get_variable('softright'))
        self.onRelim()
        self.setWindowTitle('Calibrate motor {}'.format(self.motorname))

    def onCalibrate(self):
        mot = self.credo.motors[self.motorname]
        assert isinstance(mot, Motor)
        mot.set_variable('softleft', self.leftLimitDoubleSpinBox.value())
        mot.set_variable('softright', self.rightLimitDoubleSpinBox.value())
        mot.calibrate(self.positionDoubleSpinBox.value())

    def onRelim(self):
        self.leftLimitDoubleSpinBox.setMaximum(self.rightLimitDoubleSpinBox.value())
        self.rightLimitDoubleSpinBox.setMinimum(self.leftLimitDoubleSpinBox.value())
        self.positionDoubleSpinBox.setMinimum(self.leftLimitDoubleSpinBox.value())
        self.positionDoubleSpinBox.setMaximum(self.rightLimitDoubleSpinBox.value())
