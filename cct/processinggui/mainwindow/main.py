import logging
import os
from typing import List

import appdirs
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
        self.recentMenu = QtWidgets.QMenu('Recent projects', self.menubar)
        self.actionRecent_projects.setMenu(self.recentMenu)
        self.actionClose_project.triggered.connect(self.closeProject)
        self.actionFile_list.triggered.connect(self.openFileList)
        self.actionNew_project.triggered.connect(self.createNewProject)
        self.actionPreferences.triggered.connect(self.openPreferences)
        self.actionOpen_project.triggered.connect(self.openProject)
        self.actionSave.triggered.connect(self.save)
        self.actionSave_as.triggered.connect(self.saveAs)
        self.actionQuit.triggered.connect(self.close)
        self.actionProcess.triggered.connect(self.startStopProcessing)
        self.actionReload_headers.triggered.connect(self.startStopReloadHeaders)
        self._actionsNeedingAnOpenProject = [
            self.actionClose_project, self.actionPreferences, self.actionProcess, self.actionReload_headers,
            self.actionSave, self.actionSave_as, self.actionFile_list]
        for a in self._actionsNeedingAnOpenProject:
            a.setEnabled(False)
        self.actionNew_project.trigger()
        self.loadRecentProjectList()

    def openFileList(self):
        try:
            sw = self._getSubWindow('headerview')
        except IndexError:
            hl = HeaderView(self, self.project, self.project.config)
            self._addNewSubWindow('headerview', hl)
            sw = self._getSubWindow('headerview')
        sw.show()

    def createNewProject(self) -> bool:
        # first try to close the current project
        logger.debug('Creating a new project')
        if not self.closeProject():
            # could not close the project
            return False
        logger.debug('The old project is now closed')
        assert self.project is None
        self.project = Project(self)
        logger.debug('Created a new project')
        self.project.idleChanged.connect(self.onProjectIdleChanged)
        self.project.subwindowOpenRequest.connect(self._addNewSubWindow)
        logger.debug('idleChanged signal connected.')
        self._addNewSubWindow('project', self.project)
        for a in self._actionsNeedingAnOpenProject:
            a.setEnabled(True)
        logger.debug('NEW PROJECT CREATED.')
        return True

    def save(self):
        self.project.save()

    def openProject(self):
        if self.createNewProject():
            self.project.open()

    def saveAs(self):
        self.project.saveAs()

    def openPreferences(self):
        try:
            subwindow = self._getSubWindow('settings')
        except IndexError:
            sw = SettingsWindow(self, self.project.config)
            self._addNewSubWindow('settings', sw)
            subwindow = self._getSubWindow('settings')
        subwindow.show()

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
            # note that `widget` is not the corresponding MdiSubWindow but the project itself
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
    def startStopReloadHeaders(self):
        self.project.reloadHeaders()

    @QtCore.pyqtSlot()
    def startStopProcessing(self):
        self.project.process()

    def loadRecentProjectList(self):
        logger.debug('Loading recent projects')
        configdir = appdirs.user_config_dir("cpt", "CREDO", roaming=True)
        self.recentMenu.clear()
        try:
            with open(os.path.join(configdir, 'projecthistory2'), 'rt') as f:
                for filename in f:
                    filename = filename.strip()
                    if os.path.isfile(filename):
                        logger.debug('File {} found, adding it to the recent list'.format(filename))
                        action = self.recentMenu.addAction(os.path.split(filename)[-1], self.openRecentProject)
                        action.setToolTip(filename)
                        action.setStatusTip('Open project from {}'.format(filename))
                    else:
                        logger.debug('File "{}" not found, not adding it to the recent list'.format(filename))
        except FileNotFoundError:
            logger.debug('Recent list file does not exist.')

    def openRecentProject(self):
        action = self.sender()
        assert isinstance(action, QtWidgets.QAction)
        filename = action.toolTip()
        if self.createNewProject():
            self.project.open(filename)

    def saveRecentProjectList(self):
        """Save the list of recent projects, by prepending the currently opened project"""
        logger.debug('Saving list of recent projects')
        if not self.project.windowFilePath():
            logger.debug('Not saving list of recent projects: this project does not yet have a filename')
            # the currently opened project has not yet been saved to a file.
            return
        # read the recent project list.
        configdir = appdirs.user_config_dir("cpt", "CREDO", roaming=True)
        try:
            with open(os.path.join(configdir, 'projecthistory2'), 'rt') as f:
                recentprojects = [filename.strip() for filename in f]
        except FileNotFoundError:
            # no file
            recentprojects = []
        # ensure that the current project file is at the top of the list
        recentprojects = [self.project.windowFilePath()] + [r for r in recentprojects if r != self.project.windowFilePath()]
        # write the file
        with open(os.path.join(configdir, 'projecthistory2'), 'wt') as f:
            for filename in recentprojects:
                logger.debug('Writing recent file {} to list file.'.format(filename))
                f.write(filename+'\n')
        self.loadRecentProjectList()

