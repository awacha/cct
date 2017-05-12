from PyQt5 import QtCore, QtWidgets

from .projectsetup_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.instrument.privileges import PRIV_PROJECTMAN
from ....core.services.accounting import Accounting


class ProjectSetup(QtWidgets.QWidget, Ui_Form, ToolWindow):
    required_privilege = PRIV_PROJECTMAN
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        ToolWindow.__init__(self, credo=credo)
        self._updating_ui = False
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
        self.addPushButton.setEnabled(False)
        self.removePushButton.setEnabled(False)
        self.updatePushButton.setEnabled(False)
        self.renamePushButton.setEnabled(False)
        self.onProjectSelected()


    def onProjectIDChanged(self):
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        self.addPushButton.setEnabled(self.projectIDLineEdit.text() not in acc.get_projectids())
        self.renamePushButton.setEnabled(True)

    def onProjectTitleChanged(self):
        if not self._updating_ui:
            self.updatePushButton.setEnabled(True)

    def onProposerNameChanged(self):
        if not self._updating_ui:
            self.updatePushButton.setEnabled(True)

    def onUpdateProject(self):
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        prj=self.selectedProject()
        prj.proposer=self.proposerLineEdit.text()
        prj.projectname=self.projectTitleLineEdit.text()
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
        while True:
            index += 1
            projectname = 'Untitled {:d}'.format(index)
            if projectname not in acc.get_projectids():
                acc.new_project(projectname, '', '')
                break

    def onRemoveProject(self):
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        try:
            acc.delete_project(self.selectedProject())
        except ValueError as ve:
            QtWidgets.QMessageBox.critical(self, 'Error while removing project', ve.args[0])
        self.onProjectChanged(acc)
        self.onProjectSelected()

    def onRenameProject(self):
        self._updating_ui = True
        try:
            acc = self.credo.services['accounting']
            assert isinstance(acc, Accounting)
            selected = self.selectedProject()
            newname = self.projectIDLineEdit.text()
            acc.rename_project(selected, newname)
            self.selectProject(newname)
        finally:
            self._updating_ui = False
            self.renamePushButton.setEnabled(False)

    def selectProject(self, projectid):
        self.listWidget.findItems(projectid, QtCore.Qt.MatchExactly)[0].setSelected(True)

    def onProjectChanged(self, acc: Accounting):
        self._updating_ui = True
        try:
            selected = self.selectedProject()
            self.listWidget.clear()
            self.listWidget.addItems(sorted(acc.get_projectids()))
            self.selectProject(selected)
        except IndexError:
            return
        finally:
            self._updating_ui = False

    def selectedProject(self):
        return self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)

    def onProjectSelected(self):
        self._updating_ui = True
        try:
            name = self.selectedProject()
            acc = self.credo.services['accounting']
            assert isinstance(acc, Accounting)
            prj=acc.get_project(name)
            self.projectIDLineEdit.setText(prj.projectid)
            self.projectTitleLineEdit.setText(prj.projectname)
            self.proposerLineEdit.setText(prj.proposer)
            self.removePushButton.setEnabled(True)
        except IndexError:
            self.projectIDLineEdit.setText('')
            self.projectTitleLineEdit.setText('')
            self.proposerLineEdit.setText('')
            self.removePushButton.setEnabled(True)
        finally:
            self.updatePushButton.setEnabled(False)
            self._updating_ui = False