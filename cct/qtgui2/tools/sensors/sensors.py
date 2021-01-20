from ...utils.window import WindowRequiresDevices
from PyQt5 import QtWidgets
from .sensors_ui import Ui_Form


class SensorsWindow(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(self)
        self.treeView.setModel(self.instrument.sensors)