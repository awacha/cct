from PyQt5 import QtWidgets
from ...utils.window import WindowRequiresDevices
from .pilatus_ui import Ui_Form


class PilatusDetector(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicenames = ['pilatus']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.devicemanager.detector())
