import logging
from typing import List

from PyQt5 import QtCore, QtWidgets, QtGui

from .main_ui import Ui_MainWindow
from ..headerview import HeaderView
from ..project import Project
from ..settings import SettingsWindow

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class Main(QtWidgets.QMainWindow, Ui_MainWindow):
    _actionsNeedingAnOpenProject: List[QtWidgets.QAction]
    project:Project = None

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self._actionsNeedingAnOpenProject = [
            self.actionClose_project, self.actionPreferences, self.actionProcess, self.actionReload_headers,
            self.actionSave, self.actionSave_as, self.actionFile_list]
        for a in self._actionsNeedingAnOpenProject:
            a.setEnabled(False)
        self.actionNew_project.trigger()

    @QtCore.pyqtSlot()
    def on_actionQuit_triggered(self):
        self.close()

    @QtCore.pyqtSlot()
    def on_actionFile_list_triggered(self):
        try:
            sw = self._getSubWindow('headerview')
        except IndexError:
            hl = HeaderView(self, self.project, self.project.config)
            self._addNewSubWindow('headerview', hl)
            sw = self._getSubWindow('headerview')
        sw.show()

    @QtCore.pyqtSlot()
    def on_actionNew_project_triggered(self):
        # first try to close the current project
        logger.debug('Creating a new project')
        if not self.closeProject():
            # could not close the project
            return
        logger.debug('The old project is now closed')
        assert self.project is None
        self.project = Project(self)
        logger.debug('Created a new project')
        self.project.idleChanged.connect(self.onProjectIdleChanged)
        logger.debug('idleChanged signal connected.')
        self._addNewSubWindow('project', self.project)
        for a in self._actionsNeedingAnOpenProject:
            a.setEnabled(True)
        logger.debug('NEW PROJECT CREATED.')

    @QtCore.pyqtSlot()
    def on_actionSave_triggered(self):
        self.project.save()

    @QtCore.pyqtSlot()
    def on_actionOpen_project_triggered(self):
        self.on_actionNew_project_triggered()
        self.project.open()

    @QtCore.pyqtSlot()
    def on_actionSave_as_triggered(self):
        self.project.saveAs()

    @QtCore.pyqtSlot()
    def on_actionPreferences_triggered(self):
        try:
            subwindow = self._getSubWindow('settings')
        except IndexError:
            sw = SettingsWindow(self, self.project.config)
            self._addNewSubWindow('settings', sw)
            subwindow = self._getSubWindow('settings')
        subwindow.show()

    @QtCore.pyqtSlot()
    def on_actionClose_project_triggered(self):
        self.closeProject()

    def closeProject(self) -> bool:
        logger.debug('Closing the current project')
        if self.project is None:
            logger.debug('There was no current project')
            return True
        # we have an open project. First close all _other_ subwindows.
        logger.debug('Closing non-project subwindows')
        for sw in self.mdiArea.subWindowList():
            if sw.objectName() == 'subwindow_project':
                # close 'project' last.
                continue
            logger.debug('Closing {} subwindow'.format(sw.objectName()))
            if not sw.close():
                # this subwindow refused to close (on user request), do not continue
                logger.debug('Subwindow {} refused to close'.format(sw.objectName()))
                return False
            self.mdiArea.removeSubWindow(sw)
            # process delete events.
        logger.debug('Non-project subwindows closed.')
        assert len(self.mdiArea.subWindowList()) == 1
        logger.debug('Closing project subwindow')
        sw = self._getSubWindow('project')
        if sw.close():
            self.mdiArea.removeSubWindow(sw)
            logger.debug('Closed project subwindow. Remaining subwindows: {}'.format(
                [sw.objectName() for sw in self.mdiArea.subWindowList()]))
            QtWidgets.QApplication.instance().sendPostedEvents()
            return True
        else:
            logger.debug('Project subwindow did not close')
            return False

    def _getSubWindow(self, name:str):
        return [sw for sw in self.mdiArea.subWindowList() if sw.objectName()=='subwindow_{}'.format(name)][0]

    def _addNewSubWindow(self, name:str, widget:QtWidgets.QWidget):
        # make sure that whenever a subwindow is destroyed, we remove the reference for it.
        try:
            self._getSubWindow(name)
            raise ValueError('Subwindow with name "{}" already exists'.format(name))
        except IndexError:
            # this is the expected behaviour
            pass
        subwin = self.mdiArea.addSubWindow(widget)
        subwin.setObjectName('subwindow_'+name)
        subwin.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        widget.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        subwin.show()
        subwin.destroyed.connect(self.onWidgetDestroyed)
        widget.destroyed.connect(self.onWidgetDestroyed)
        return

    def onWidgetDestroyed(self, widget:QtWidgets.QWidget):
        logger.debug('Widget {} destroyed'.format(widget.objectName()))
        logger.debug('Subwindows alive: {}'.format([sw.objectName() for sw in self.mdiArea.subWindowList()]))
        if widget.objectName() == 'projectWindow':
            logger.debug('Deleting all subwindows')
            for subwindow in self.mdiArea.subWindowList():
                subwindow.close()
            logger.debug('Deleting self.project')
            self.project = None
            for action in self._actionsNeedingAnOpenProject:
                action.setEnabled(False)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        logger.debug('Main window close requested, trying to close project.')
        if self.closeProject(): # close the project: it implies closing all other subwindows
            event.accept()
        else:
            event.ignore()

    def onProjectIdleChanged(self, idle:bool):
        for widget in [self.actionSave_as, self.actionSave, self.actionReload_headers, self.actionRecent_projects, self.actionProcess,
                       self.actionPreferences, self.actionClose_project, self.actionNew_project, self.actionOpen_project, self.actionQuit]:
            widget.setEnabled(idle)

    @QtCore.pyqtSlot()
    def on_actionReload_headers_triggered(self):
        self.project.reloadHeaders()

    @QtCore.pyqtSlot()
    def on_actionProcess_triggered(self):
        self.project.process()