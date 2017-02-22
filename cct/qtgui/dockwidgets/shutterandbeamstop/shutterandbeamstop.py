from PyQt5 import QtWidgets

from .shutterandbeamstop_ui import Ui_DockWidget
from ...core.mixins import ToolWindow


class ShutterAndBeamstop(QtWidgets.QDockWidget, Ui_DockWidget, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QDockWidget.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo)
        self.setupUi(self)

    def setupUi(self, DockWidget):
        Ui_DockWidget.setupUi(self, self)
