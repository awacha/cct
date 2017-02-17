from PyQt5 import QtWidgets

from .sampleeditor_ui import Ui_Form


class SampleEditor(QtWidgets.QWidget, Ui_Form):
    def __init__(self, *args, **kwargs):
        self.credo=kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupUi(self)

