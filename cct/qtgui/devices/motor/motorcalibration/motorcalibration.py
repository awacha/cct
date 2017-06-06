from PyQt5 import QtWidgets

from .motorcalibration_ui import Ui_Form
from ....core.mixins import ToolWindow
from .....core.instrument.privileges import PRIV_MOTORCALIB


class MotorCalibration(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_privilege = PRIV_MOTORCALIB
    pass
