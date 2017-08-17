import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from PyQt5 import QtWidgets
from .accounting_ui import Ui_DockWidget
from ...core.mixins import ToolWindow
from ....core.instrument.instrument import Instrument
from ....core.services.accounting import Accounting as AccountingService


class Accounting(QtWidgets.QDockWidget, Ui_DockWidget, ToolWindow):
    def __init__(self, *args, **kwargs):
        self._accountingserviceconnections = []
        credo = kwargs.pop('credo')
        QtWidgets.QDockWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, DockWidget):
        assert not self._accountingserviceconnections
        Ui_DockWidget.setupUi(self, DockWidget)
        assert isinstance(self.credo, Instrument)
        a = self.credo.services['accounting']
        assert isinstance(a, AccountingService)
        self.operatorNameLabel.setText(a.get_user().username)
        self.privilegesComboBox.clear()
        self.privilegesComboBox.addItems(a.get_accessible_privlevels_str())
        self.onPrivilegeChanged(a, a.get_privilegelevel())
        self.privilegesComboBox.currentTextChanged.connect(self.onPrivilegeChange)
        self.onProjectChanged(a)
        self.projectIDComboBox.currentTextChanged.connect(self.onProjectChange)
        self._accountingserviceconnections = [
            a.connect('privlevel-changed', self.onPrivilegeChanged),
            a.connect('project-changed', self.onProjectChanged)
        ]

    def onProjectChange(self):
        a = self.credo.services['accounting']
        if a.get_project().projectid == self.projectIDComboBox.currentText():
            return
        assert isinstance(a, AccountingService)
        logger.debug('Selecting project: {}'.format(self.projectIDComboBox.currentText()))
        a.select_project(self.projectIDComboBox.currentText())

    def onProjectChanged(self, accounting: AccountingService):
        project = accounting.get_project()
        self.proposerNameLabel.setText(project.proposer)
        self.projectTitleLabel.setText(project.projectname)
        self.projectIDComboBox.blockSignals(True)
        self.projectIDComboBox.clear()
        self.projectIDComboBox.addItems(accounting.get_projectids())
        self.projectIDComboBox.blockSignals(False)
        self.projectIDComboBox.setCurrentIndex(self.projectIDComboBox.findText(project.projectid))

    def onPrivilegeChange(self):
        a = self.credo.services['accounting']
        assert isinstance(a, AccountingService)
        a.set_privilegelevel(self.privilegesComboBox.currentText())

    def onPrivilegeChanged(self, accounting: AccountingService, privlevel):
        self.privilegesComboBox.setCurrentIndex(self.privilegesComboBox.findText(privlevel.name))

    def cleanup(self):
        super().cleanup()
        try:
            for c in self._accountingserviceconnections:
                self.credo.services['accounting'].disconnect(c)
            self._accountingserviceconnections = []
        except AttributeError:
            pass
