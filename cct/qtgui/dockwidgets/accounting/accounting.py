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
        self.onProjectChanged(a)
        self._accountingserviceconnections = [
            a.connect('privlevel-changed', self.onPrivilegeChanged),
            a.connect('project-changed', self.onProjectChanged)
        ]

    def onProjectChange(self):
        """This is a callback emitted by the project ID combo box if the user changes the selected project.

        This function must change the active project in the the accounting service
        """
        a = self.credo.services['accounting']
        assert isinstance(a, AccountingService)
        selectedprojectid=self.projectIDComboBox.currentText() # this is the project ID of the selected project.
        if not selectedprojectid:
            # in the case of an invalid selection, do nothing
            return
        logger.debug('The user has selected the project with the projectid: {}'.format(selectedprojectid))
        if a.get_project().projectid == selectedprojectid:
            # if the project is already selected, do nothing.
            return
        logger.debug('Selecting project: {}'.format(selectedprojectid))
        # select the project. This in turn will emit the project-changed signal, calling self.onProjectChanged()
        a.select_project(selectedprojectid)

    def onProjectChanged(self, accounting: AccountingService):
        """Callback from the accounting service: either the project list changed, or one project is modified, or another
        project has been selected as the active one.

        The task of this function is to set the UI elements (project ID combo box, project title, proposer name.

        Under no condition should this result in the emission of the currentIndexChanged() signal of the project ID
        combo box, as it will change the current project
        """
        project = accounting.get_project() # this is the active project
        logger.debug('OnProjectChanged. Active project from the accounting service: {}'.format(project.projectid))
        self.proposerNameLabel.setText(project.proposer)
        self.projectTitleLabel.setText(project.projectname)
        # now update the project ID combobox
        self.projectIDComboBox.blockSignals(True)
        try:
            self.projectIDComboBox.clear()
            self.projectIDComboBox.addItems(sorted(accounting.get_projectids()))
            newindex = self.projectIDComboBox.findText(project.projectid)
            logger.debug('Index of the current project ({}) in the combo box: {}'.format(project.projectid, newindex))
            self.projectIDComboBox.setCurrentIndex(newindex)
        finally:
            logger.debug('Turning signals of the project ID combo box back on')
            self.projectIDComboBox.blockSignals(False)

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
