from PySide6 import QtWidgets
from .motorcalibration_ui import Ui_Dialog
from ....core2.instrument.instrument import Instrument


class MotorCalibrationDialog(QtWidgets.QDialog, Ui_Dialog):
    motorname: str

    def __init__(self, **kwargs):
        self.motorname = kwargs.pop('motorname')
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Dialog):
        super().setupUi(Dialog)
        self.setWindowTitle(f'Calibrate motor {self.motorname}')
        motor = Instrument.instance().motors[self.motorname]
        self.leftLimitDoubleSpinBox.setValue(motor['softleft'])
        self.rightLimitDoubleSpinBox.setValue(motor['softright'])
        self.positionDoubleSpinBox.setValue(motor['actualposition'])

    def leftLimit(self) -> float:
        return self.leftLimitDoubleSpinBox.value()

    def rightLimit(self) -> float:
        return self.rightLimitDoubleSpinBox.value()

    def position(self) -> float:
        return self.positionDoubleSpinBox.value()
