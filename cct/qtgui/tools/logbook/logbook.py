import datetime
import os

from PyQt5 import QtWidgets

from .logbook_ui import Ui_Form
from .logbookmodel import LogBookModel
from ...core.mixins import ToolWindow


class LogBook(QtWidgets.QWidget, Ui_Form, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        self.model = LogBookModel(self.logTreeView, os.path.join(self.credo.config['path']['directories']['log'], 'userlog.pickle'))
        self.submitPushButton.clicked.connect(self.onSubmit)
        self.logTreeView.setModel(self.model)

    def onSubmit(self):
        if self.customDateRadioButton.isChecked():
            date = self.dateTimeEdit.dateTime().toPyDateTime()
        else:
            date = datetime.datetime.now()
        self.model.addLogEntry(date, self.credo.services['accounting'].get_user().username, self.logMessagePlainTextEdit.toPlainText())
