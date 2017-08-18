from PyQt5 import QtWidgets

from .commandhelp_ui import Ui_Form
from ..core.mixins import ToolWindow
from ...core.commands import Command


class CommandHelp(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.listWidget.addItems(list(sorted([c.name for c in Command.allcommands()])))
        self.listWidget.currentItemChanged.connect(self.onCommandSelected)
        self.listWidget.setMaximumWidth(self.listWidget.sizeHintForColumn(0)+30)
        self.listWidget.setMinimumWidth(self.listWidget.sizeHintForColumn(0)+20)
        self.listWidget.setCurrentRow(0)
        self.adjustSize()


    def onCommandSelected(self):
        cmdname=self.listWidget.currentItem().text()
        cmd = [c for c in Command.allcommands() if c.name==cmdname][0]
        assert issubclass(cmd, Command)
        self.textBrowser.clear()
        self.textBrowser.setPlainText(cmd.__doc__)
