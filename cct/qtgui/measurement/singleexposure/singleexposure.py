from PyQt5 import QtWidgets, QtGui

from .singleexposure_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.services.interpreter import Interpreter


class SingleExposure(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_devices = ['genix', 'pilatus']

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo)
        self._failed = False
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.progressBar.setVisible(False)
        self.prefixComboBox.currentIndexChanged.connect(self.onPrefixChanged)

    def onPrefixChanged(self):
        pass

    def onExpose(self):
        pass

    def onCmdReturn(self, interpreter:Interpreter, cmdname:str, retval):
        pass

    def onCmdFail(self, interpreter:Interpreter, cmdname:str, exception:Exception, traceback:str):
        self._failed = True

    def setIdle(self):
        super().setIdle()
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/exposure.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.exposePushButton.setIcon(icon)
        self.exposePushButton.setText('Expose')

    def setBusy(self):
        super().setBusy()
        self.exposePushButton.setText('Stop')
        self.exposePushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
        self.entryWidget.setEnabled(False)
