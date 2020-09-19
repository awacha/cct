from PyQt5 import QtWidgets
from .beamstop_ui import Ui_Frame


class BeamstopIndicator(QtWidgets.QFrame, Ui_Frame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Frame):
        super().setupUi(Frame)