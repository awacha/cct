import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from PyQt5 import QtWidgets
from .accounting_ui import Ui_DockWidget
from .projectsmodel import ProjectsModel
from ...core.mixins import ToolWindow
from ....core.instrument.instrument import Instrument
from ....core.services.accounting import Accounting as AccountingService
from ....core.utils.inhibitor import Inhibitor


class Accounting(QtWidgets.QDockWidget, Ui_DockWidget, ToolWindow):
    def __init__(self, *args, **kwargs):
        self._accountingserviceconnections = []
        self._updating = Inhibitor()
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
        self.projectsModel = ProjectsModel(self.credo)
        self.projectsView = QtWidgets.QTreeView(self.projectIDComboBox)
        self.projectsView.setRootIsDecorated(False)
        self.projectsView.setHeaderHidden(True)
        self.projectsView.setAllColumnsShowFocus(True)
        self.projectsView.setAlternatingRowColors(True)
        self.projectsView.setWordWrap(True)
        self.projectsView.resizeColumnToContents(0)
        self.projectsView.resizeColumnToContents(1)
        self.projectsView.setMinimumWidth(300)
        self.projectIDComboBox.setModel(self.projectsModel)
        self.projectIDComboBox.setView(self.projectsView)
        self.projectIDComboBox.setSizeAdjustPolicy(self.projectIDComboBox.AdjustToContents)
        self.projectIDComboBox.setModelColumn(0)
        self.projectIDComboBox.currentIndexChanged.connect(self.onProjectChange)
        self._accountingserviceconnections = [
            a.connect('privlevel-changed', self.onPrivilegeChanged),
            a.connect('project-changed', self.onProjectChanged)
        ]

    def onProjectChange(self):
        if self._updating:
            return
        a = self.credo.services['accounting']
        assert isinstance(a, AccountingService)
        selectedprojectid=sorted(a.get_projectids())[self.projectIDComboBox.currentIndex()]
        logger.debug('selectedprojectid: {}'.format(selectedprojectid))
        if a.get_project().projectid == selectedprojectid:
            return
        logger.debug('Selecting project: {}'.format(selectedprojectid))
        with self._updating:
            a.select_project(selectedprojectid)

    def onProjectChanged(self, accounting: AccountingService):
        project = accounting.get_project()
        logger.debug('OnProjectChanged: {}'.format(project.projectid))
        self.proposerNameLabel.setText(project.proposer)
        self.projectTitleLabel.setText(project.projectname)
        self.projectIDComboBox.blockSignals(True)
#        self.projectIDComboBox.clear()
#        self.projectIDComboBox.addItems(accounting.get_projectids())
        self.projectIDComboBox.blockSignals(False)
        newindex = sorted(accounting.get_projectids()).index(project.projectid)
        logger.debug('newindex: {}'.format(newindex))
        self.projectIDComboBox.setCurrentIndex(newindex)

    def onPrivilegeChange(self):
        a = self.credo.services['accounting']
        assert isinstance(a, AccountingService)
        a.set_privilegelevel(self.privilegesComboBox.currentText())

    def onPrivilegeChanged(self, accounting: AccountingService, privlevel):
        self.privilegesComboBox.setCurrentIndex(self.privilegesComboBox.findText(privlevel.name))

    def cleanup(self):
        super().cleanup()
        self.projectsModel.cleanup()
        try:
            for c in self._accountingserviceconnections:
                self.credo.services['accounting'].disconnect(c)
            self._accountingserviceconnections = []
        except AttributeError:
            pass
