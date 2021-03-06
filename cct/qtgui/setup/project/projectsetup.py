import logging

from PyQt5 import QtCore, QtWidgets

from .projectsetup_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.instrument.privileges import PRIV_PROJECTMAN
from ....core.services.accounting import Accounting
from ....core.utils.inhibitor import Inhibitor

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ProjectSetup(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_privilege = PRIV_PROJECTMAN

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo=credo)
        self._updating_ui = Inhibitor(max_inhibit=1)
        self._acc_connections = []
        self.setupUi(self)

    def setupUi(self, Form):
        Ui_Form.setupUi(self, Form)
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        self.listWidget.addItems(sorted(acc.get_projectids()))
        self.listWidget.item(0).setSelected(True)
        self.addPushButton.clicked.connect(self.onAddProject)
        self.removePushButton.clicked.connect(self.onRemoveProject)
        self.renamePushButton.clicked.connect(self.onRenameProject)
        self._acc_connections = [acc.connect('project-changed', self.onProjectChanged)]
        self.listWidget.itemSelectionChanged.connect(self.onProjectSelected)
        self.updatePushButton.clicked.connect(self.onUpdateProject)
        self.projectIDLineEdit.textChanged.connect(self.onProjectIDChanged)
        self.proposerLineEdit.textChanged.connect(self.onProposerNameChanged)
        self.projectTitleLineEdit.textChanged.connect(self.onProjectTitleChanged)
        self.addPushButton.setEnabled(True)
        self.removePushButton.setEnabled(False)
        self.updatePushButton.setEnabled(False)
        self.renamePushButton.setEnabled(False)
        self.onProjectSelected()

    def onProjectIDChanged(self):
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        self.renamePushButton.setEnabled(True)

    def onProjectTitleChanged(self):
        if not self._updating_ui:
            self.updatePushButton.setEnabled(True)

    def onProposerNameChanged(self):
        if not self._updating_ui:
            self.updatePushButton.setEnabled(True)

    def onUpdateProject(self):
        logger.debug('Updating project')
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        acc.update_project(self.selectedProjectName(),
                           self.projectTitleLineEdit.text(),
                           self.proposerLineEdit.text())
        self.updatePushButton.setEnabled(False)

    def cleanup(self):
        for c in self._acc_connections:
            self.credo.services['accounting'].disconnect(c)
        self._acc_connections = []
        super().cleanup()

    def onAddProject(self):
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        index = 0
        projectname=None
        while True:
            index += 1
            projectname = 'Untitled {:d}'.format(index)
            if projectname not in acc.get_projectids():
                break
        acc.new_project(projectname, '', '')
        # the previous command emits the project-changed signal.
        self.selectProject(projectname)

    def onRemoveProject(self):
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        try:
            acc.delete_project(self.selectedProjectName())
        except ValueError as ve:
            QtWidgets.QMessageBox.critical(self, 'Error while removing project', ve.args[0])
        self.onProjectChanged(acc)
        self.onProjectSelected()

    def onRenameProject(self):
        logger.debug('onRenameProject()')
        self.renamePushButton.setEnabled(False)
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        selected = self.selectedProjectName()
        newname = self.projectIDLineEdit.text()
        try:
            acc.rename_project(selected, newname)
        except ValueError as ve:
            QtWidgets.QMessageBox.critical(self, 'Cannot rename project',
                                           'Cannot rename project: {}'.format(ve.args[0]))
            return
        self.selectProject(newname)

    def selectProject(self, projectid):
        item=self.listWidget.findItems(projectid, QtCore.Qt.MatchExactly)[0]
        item.setSelected(True)
        self.listWidget.scrollToItem(item)

    def onProjectChanged(self, acc: Accounting):
        """Callback function, called when the project list is changed: either a project is modified
        or one is added or removed"""
        logger.debug('onProjectChanged()')
        with self._updating_ui:
            try:
                selected = self.selectedProjectName() # try to keep the currently selected project
                # update the project name list in the list widget
                self.listWidget.clear()
                self.listWidget.addItems(sorted(acc.get_projectids()))
            except IndexError:
                return
        try:
            self.selectProject(selected)
        except IndexError:
            # if the project has been removed, select the first one.
            self.listWidget.setCurrentRow(0)
            return

    def selectedProjectName(self):
        return self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)

    def selectedProject(self):
        return self.credo.services['accounting'].get_project(self.selectedProjectName())

    def onProjectSelected(self):
        if self._updating_ui.inhibited:
            logger.debug('Already inhibited')
            return
        with self._updating_ui:
            try:
                self.updatePushButton.setEnabled(False)
                name = self.selectedProjectName()
                acc = self.credo.services['accounting']
                assert isinstance(acc, Accounting)
                prj = acc.get_project(name)
                self.projectIDLineEdit.setText(prj.projectid)
                self.projectTitleLineEdit.setText(prj.projectname)
                self.proposerLineEdit.setText(prj.proposer)
                self.removePushButton.setEnabled(True)
            except IndexError:
                self.projectIDLineEdit.setText('')
                self.projectTitleLineEdit.setText('')
                self.proposerLineEdit.setText('')
                self.removePushButton.setEnabled(True)
