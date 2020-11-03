from typing import Optional

from PyQt5 import QtWidgets, QtCore
from .main_ui import Ui_MainWindow
from ...core2.processing.processing import Processing
from .project import ProjectWindow
from .averaging import AveragingWindow
from .headers import HeadersWindow


class Main(QtWidgets.QMainWindow, Ui_MainWindow):
    project: Optional[Processing] = None
    averagingwindow: Optional[AveragingWindow] = None
    projectwindow: Optional[ProjectWindow] = None
    headerswindow: Optional[HeadersWindow] = None

    def __init__(self):
        super().__init__()
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.actionSave.triggered.connect(self.saveProject)
        self.actionNew_project.triggered.connect(self.newProject)
        self.actionClose.triggered.connect(self.closeProject)
        self.actionSave_as.triggered.connect(self.saveProjectAs)
        self.actionOpen_project.triggered.connect(self.openProject)
        self.newProject()

    def saveProject(self) -> bool:
        self.project.save()

    def newProject(self):
        if not self.confirmCloseProject():
            return
        self.project = Processing()
        self.createProjectWindows()

    def openProject(self):
        pass

    def saveProjectAs(self):
        pass

    def closeProject(self):
        if not self.confirmCloseProject():
            return
        self.project.deleteLater()
        self.project = None

    def confirmCloseProject(self) -> bool:
        if self.project is None:
            return True
        result = QtWidgets.QMessageBox.question(
            self, 'Project changed', 'Abandon unsaved changes and close the project?', QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel)
        if result == QtWidgets.QMessageBox.Yes:
            return True
        elif result == QtWidgets.QMessageBox.No:
            return self.saveProject()
        elif result == QtWidgets.QMessageBox.Cancel:
            return False
        else:
            assert False

    def createProjectWindows(self):
        self.destroyProjectWindows()
        self.averagingwindow = AveragingWindow(self.project)
        self.projectwindow = ProjectWindow(self.project)
        self.headerswindow = HeadersWindow(self.project)
        for widget in [self.averagingwindow, self.projectwindow, self.headerswindow]:
            sw = self.mdiArea.addSubWindow(widget)
            sw.showNormal()

    def destroyProjectWindows(self):
        for widget in [self.averagingwindow, self.projectwindow, self.headerswindow]:
            if widget is not None:
                self.mdiArea.removeSubWindow(widget)
                widget.destroy(True, True)
        self.averagingwindow = None
        self.projectwindow = None
        self.headerswindow = None
