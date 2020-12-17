import itertools
import time
from typing import Optional, List, Dict
import logging

from PyQt5 import QtWidgets, QtCore
from .main_ui import Ui_MainWindow
from ...core2.processing.processing import Processing
from .project import ProjectWindow
from .averaging import AveragingWindow
from .headers import HeadersWindow
from .results import ResultsWindow
from .subtraction import SubtractionWindow
from .resultviewwindow import ResultViewWindow
from .merging import MergingWindow
from .closablemdisubwindow import ClosableMdiSubWindow

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Main(QtWidgets.QMainWindow, Ui_MainWindow):
    project: Optional[Processing] = None
    averagingwindow: Optional[AveragingWindow] = None
    projectwindow: Optional[ProjectWindow] = None
    headerswindow: Optional[HeadersWindow] = None
    resultswindow: Optional[ResultsWindow] = None
    subtractionwindow: Optional[SubtractionWindow] = None
    mergingwindow: Optional[MergingWindow] = None
    viewwindows: Dict[str, ResultViewWindow]

    def __init__(self):
        super().__init__()
        self.viewwindows = {}
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.actionSave.triggered.connect(self.saveProject)
        self.actionNew_project.triggered.connect(self.newProject)
        self.actionClose.triggered.connect(self.closeProject)
        self.actionSave_as.triggered.connect(self.saveProjectAs)
        self.actionOpen_project.triggered.connect(self.openProject)
        self.actionQuit.triggered.connect(self.close)
        for action in [self.actionProject_window, self.actionCollect, self.actionBackground, self.actionMerge, self.actionResults, self.actionMetadata]:
            action.triggered.connect(self.onShowHideProjectWindow)
            action.setEnabled(False)

    def onShowHideProjectWindow(self, checked: bool):
        if self.project is None:
            return
        elif self.sender() is self.actionProject_window:
            window = self.projectwindow
        elif self.sender() is self.actionCollect:
            window = self.averagingwindow
        elif self.sender() is self.actionBackground:
            window = self.subtractionwindow
        elif self.sender() is self.actionMerge:
            window = self.mergingwindow
        elif self.sender() is self.actionResults:
            window = self.resultswindow
        elif self.sender() is self.actionMetadata:
            window = self.headerswindow
        else:
            # should not happen. But if it happens, ignore and return gracefully
            return
        assert window is not None
        window.parent().setVisible(checked)

    def onSubWindowHidden(self, widget: QtWidgets.QWidget):
        subwindow = self.sender()
        assert isinstance(subwindow, ClosableMdiSubWindow)
        if widget is self.projectwindow:
            action = self.actionProject_window
        elif subwindow.widget() is self.averagingwindow:
            action = self.actionCollect
        elif subwindow.widget() is self.subtractionwindow:
            action = self.actionBackground
        elif subwindow.widget() is self.mergingwindow:
            action = self.actionMerge
        elif subwindow.widget() is self.resultswindow:
            action = self.actionResults
        elif subwindow.widget() is self.headerswindow:
            action = self.actionMetadata
        else:
            raise ValueError(f'Unknown subwindow: {subwindow.window().objectName()=}, {type(subwindow.widget())}, {subwindow.objectName()=}, {type(subwindow)}')
        action.blockSignals(True)
        action.setChecked(False)
        action.blockSignals(False)

    def saveProject(self) -> bool:
        if not self.windowFilePath():
            return self.saveProjectAs()
        else:
            self.project.save(self.windowFilePath())
            self.project.setModified(False)
            return True

    def newProject(self):
        if not self.confirmCloseProject():
            return
        else:
            self.closeProject()
        filename, filter_ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save the new CPT project to', '', 'CPT4 project files (*.cpt4);;Old-style CPT project files (*.cpt *.cpt2);;All files (*)', 'CPT4 project files (*.cpt4)')
        if not filename:
            return
        if not filename.lower().endswith('.cpt4'):
            filename = filename+'.cpt4'
        self.project = Processing(filename)
        self.createProjectWindows()
        self.setWindowFilePath(self.project.settings.filename)
        self.project.setModified(False)

    @QtCore.pyqtSlot()
    def openProject(self, filename: Optional[str]=None):
        if not self.confirmCloseProject():
            return
        if filename is None:
            filename, filter_ = QtWidgets.QFileDialog.getOpenFileName(self, 'Open a CPT project file', '', 'CPT4 project files (*.cpt4);;Old-style CPT project files (*.cpt *.cpt2);;All files (*)', 'CPT4 project files (*.cpt4)')
            if not filename:
                return
        self.project = Processing.fromFile(filename)
        self.setWindowFilePath(filename)
        self.createProjectWindows()
        self.project.setModified(False)

    def saveProjectAs(self) -> bool:  # True if saved successfully
        filename, filter_ = QtWidgets.QFileDialog.getSaveFileName(self, 'Select a file to save the project to', '', 'CPT4 project files (*.cpt4);;All files (*)', 'CPT4 project files (*.cpt4)')
        if not filename:
            return False
        self.setWindowFilePath(filename)
        return self.saveProject()

    def closeProject(self):
        if not self.confirmCloseProject():
            return
        self.destroyProjectWindows()
        if self.project is not None:
            self.project.deleteLater()
        self.project = None
        self.setWindowFilePath('')

    def confirmCloseProject(self) -> bool:
        if (self.project is None) or (not self.project.modified()):
            return True
        result = QtWidgets.QMessageBox.question(
            self, 'Project changed', 'Abandon unsaved changes and close the project?', QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel)
        if result == QtWidgets.QMessageBox.Yes:
            self.project.setModified(False)
            return True
        elif result == QtWidgets.QMessageBox.No:
            return self.saveProject()
        elif result == QtWidgets.QMessageBox.Cancel:
            return False
        else:
            assert False

    def createProjectWindows(self):
        logger.debug('CreateProjectWindows called')
        self.destroyProjectWindows()
        self.projectwindow = ProjectWindow(self.project, self)
        self.headerswindow = HeadersWindow(self.project, self)
        self.averagingwindow = AveragingWindow(self.project, self)
        self.resultswindow = ResultsWindow(self.project, self)
        self.subtractionwindow = SubtractionWindow(self.project, self)
        self.mergingwindow = MergingWindow(self.project, self)
        for widget in [self.projectwindow, self.headerswindow, self.averagingwindow, self.resultswindow, self.subtractionwindow, self.mergingwindow]:
            sw = ClosableMdiSubWindow()
            sw.setWidget(widget)
            self.mdiArea.addSubWindow(sw)
            widget.destroyed.connect(self.onWidgetDestroyed)
            sw.setWindowIcon(widget.windowIcon())
            sw.close()
            sw.hidden.connect(self.onSubWindowHidden)
        for action in [self.actionProject_window, self.actionMetadata, self.actionCollect, self.actionResults, self.actionBackground, self.actionMerge]:
            action.setEnabled(True)
            action.setChecked(False)
        self.actionProject_window.setChecked(True)
        self.projectwindow.showNormal()
        #self.mdiArea.cascadeSubWindows()
        self.project.modificationChanged.connect(self.onProjectModified)

    def destroyProjectWindows(self):
        logger.debug('Destroying project windows')
        for widget in itertools.chain([self.averagingwindow, self.projectwindow, self.headerswindow, self.resultswindow, self.subtractionwindow, self.mergingwindow], self.viewwindows.values()):
            if widget is not None:
                logger.debug(f'Removing an MDI subwindow for widget {widget=}')
                self.mdiArea.removeSubWindow(widget.parent())
                widget.destroy(True, True)
                widget.deleteLater()
        for action in [self.actionProject_window, self.actionMetadata, self.actionCollect, self.actionResults, self.actionBackground, self.actionMerge]:
            action.blockSignals(True)
            action.setEnabled(False)
            action.setChecked(False)
            action.blockSignals(False)
        self.averagingwindow = None
        self.projectwindow = None
        self.headerswindow = None
        self.resultswindow = None
        self.subtractionwindow = None
        self.mergingwindow = None
        self.viewwindows = {}

    def onProjectModified(self, modified: bool):
        pass

    def createViewWindow(self, widget: QtWidgets.QWidget, handlestring: str):
        if handlestring not in self.viewwindows:
            self.viewwindows[handlestring] = widget
            subwindow = self.mdiArea.addSubWindow(self.viewwindows[handlestring])
            self.viewwindows[handlestring].setObjectName(self.viewwindows[handlestring].objectName()+f'__{time.monotonic()}')
            self.viewwindows[handlestring].destroyed.connect(self.onWidgetDestroyed)
            subwindow.setWindowIcon(self.viewwindows[handlestring].windowIcon())
        self.viewwindows[handlestring].raise_()
        self.viewwindows[handlestring].showNormal()
        #self.viewwindows[handlestring].setFocus()

    def onWidgetDestroyed(self, object:QtWidgets.QWidget):
        for key in list(self.viewwindows):
            try:
                self.viewwindows[key].objectName()
            except RuntimeError:
                logger.debug(f'Removing {key} from the view windows dictionary because the wrapped C/C++ object has been deleted')
                del self.viewwindows[key]
                continue
            if self.viewwindows[key].objectName() == object.objectName():
                del self.viewwindows[key]
                logger.debug(f'Removed {key} from the view windows dictionary')
                break
        for subwin in self.mdiArea.subWindowList():
            if subwin.widget() is None:
                logger.debug('Destroying an empty subwindow.')
                subwin.destroy(True, True)

