from PyQt5 import QtWidgets
from .shutter_ui import Ui_Frame


class ShutterIndicator(QtWidgets.QFrame, Ui_Frame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Frame):
        super().setupUi(Frame)