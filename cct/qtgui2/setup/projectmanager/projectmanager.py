from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Slot

from .projectmanager_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.auth import Privilege


class ProjectManager(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.projectListTreeView.setModel(self.instrument.projects)
        self.addProjectPushButton.clicked.connect(self.addProject)
        self.removeProjectPushButton.clicked.connect(self.removeProject)
        self.projectListTreeView.selectionModel().selectionChanged.connect(self.projectSelected)
        for c in range(self.projectListTreeView.model().columnCount()):
            self.projectListTreeView.resizeColumnToContents(c)
        self.addProjectPushButton.setEnabled(self.instrument.auth.hasPrivilege(Privilege.ProjectManagement))
        self.removeProjectPushButton.setEnabled(self.instrument.auth.hasPrivilege(Privilege.ProjectManagement))

    @Slot()
    def addProject(self):
        prjid, ok = QtWidgets.QInputDialog.getText(self, 'Create a new project', 'Name of the new project:')
        if not ok:
            return
        self.instrument.projects.addProject(projectid=prjid)

    @Slot()
    def removeProject(self):
        if self.projectListTreeView.selectionModel().currentIndex().isValid():
            self.instrument.projects.removeProject(
                self.projectListTreeView.selectionModel().currentIndex().data(QtCore.Qt.ItemDataRole.UserRole).projectid
            )

    @Slot()
    def projectSelected(self):
        if not self.projectListTreeView.selectionModel().currentIndex().isValid():
            self.removeProjectPushButton.setEnabled(False)
        else:
            self.removeProjectPushButton.setEnabled(
                (self.projectListTreeView.selectionModel().currentIndex().data(QtCore.Qt.ItemDataRole.UserRole).projectid !=
                 self.instrument.projects.projectID()) and self.instrument.auth.hasPrivilege(
                    Privilege.ProjectManagement))
