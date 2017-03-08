from PyQt5 import QtCore, QtWidgets

from .projectsetup_ui import Ui_Form
from ...core.mixins import ToolWindow
from ....core.services.accounting import Accounting


class ProjectSetup(QtWidgets.QWidget, Ui_Form, ToolWindow):
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

    def selectProject(self, projectid):
        self.listWidget.findItems(projectid, QtCore.Qt.MatchExactly)[0].setSelected(True)

    def onProjectChanged(self, acc: Accounting):
        self._updating_ui = True
        try:
            selected = self.selectedProject()
            self.listWidget.clear()
            self.listWidget.addItems(sorted(acc.get_projectids()))
            self.selectedProject(selected)
        except IndexError:
            return
        finally:
            self._updating_ui = False

    def selectedProject(self):
        return self.listWidget.selectedItems()[0].data(QtCore.Qt.DisplayRole)
