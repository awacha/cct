import weakref

from PyQt5 import QtWidgets

from .mainwindow_ui import Ui_MainWindow
from ..setup.sampleeditor import SampleEditor
from ..tools.capillarymeasurement import CapillaryMeasurement
from ..tools.maskeditor import MaskEditor


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, *args, **kwargs):
        self.credo=kwargs.pop('credo')
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        self.windowdict={}
        self.setupUi(self)

    def setupUi(self, MainWindow):
        Ui_MainWindow.setupUi(self,MainWindow)
        self.actionQuit.triggered.connect(self.onQuit)
        for action, windowclass in [(self.actionSample_editor, SampleEditor),
                                    (self.actionMask_editor, MaskEditor),
                                    (self.actionCapillary_sizing, CapillaryMeasurement),]:
            assert isinstance(action, QtWidgets.QAction)
            action.triggered.connect(lambda a=action, wc=windowclass: self.openWindow(a,wc))

    def onQuit(self):
        self.close()

    def openWindow(self, action, windowclass):
        try:
            self.windowdict[action].show()
        except KeyError:
            self.windowdict[action]=windowclass(parent=None, credo=weakref.proxy(self.credo))
            return self.openWindow(action, windowclass)
        return True
