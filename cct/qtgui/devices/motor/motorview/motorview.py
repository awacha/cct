from PyQt5 import QtWidgets

from .motorlist import MotorModel
from .motorview_ui import  Ui_Form
from ....core.mixins import ToolWindow
from .....core.instrument.instrument import Instrument


class MotorOverview(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, parent, credo):
        QtWidgets.QWidget.__init__(self, parent)
        assert isinstance(credo, Instrument)
        ToolWindow.__init__(self, credo, required_devices=['Motor_'+m for m in credo.motors])
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.motorModel = MotorModel(credo=self.credo)
        self.treeView.setModel(self.motorModel)
