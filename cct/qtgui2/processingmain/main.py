import collections
import logging
import os
import time
from typing import Optional, Dict, Final, List, Tuple, Type

import appdirs
from PyQt5 import QtWidgets, QtCore, QtGui

from .averaging import AveragingWindow
from .closablemdisubwindow import ClosableMdiSubWindow
from .headers import HeadersWindow
from .main_ui import Ui_MainWindow
from .merging import MergingWindow
from .project import ProjectWindow
from .results import ResultsWindow
from .resultviewwindow import ResultViewWindow
from .settings import SettingsWindow
from .subtraction import SubtractionWindow
from ...core2.processing.processing import Processing

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

WindowInfo = collections.namedtuple('WindowInfo', ['attribute', 'windowclass', 'action'])


class Main(QtWidgets.QMainWindow, Ui_MainWindow):
    project: Optional[Processing] = None
    averagingwindow: Optional[AveragingWindow] = None
    projectwindow: Optional[ProjectWindow] = None
    headerswindow: Optional[HeadersWindow] = None
    resultswindow: Optional[ResultsWindow] = None
    subtractionwindow: Optional[SubtractionWindow] = None
    mergingwindow: Optional[MergingWindow] = None
    viewwindows: Dict[str, ResultViewWindow]
    settingswindow: Optional[SettingsWindow] = None

    windowinfo: Final[List[WindowInfo]] = [
        WindowInfo('projectwindow', ProjectWindow, 'actionProject_window'),
        WindowInfo('headerswindow', HeadersWindow, 'actionMetadata'),
        WindowInfo('averagingwindow', AveragingWindow, 'actionCollect'),
        WindowInfo('subtractionwindow', SubtractionWindow, 'actionBackground'),
        WindowInfo('resultswindow', ResultsWindow, 'actionResults'),
        WindowInfo('mergingwindow', MergingWindow, 'actionMerge'),
        WindowInfo('settingswindow', SettingsWindow, 'actionPreferences'),
    ]

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
        for actionname in [wi.action for wi in self.windowinfo]:
            action = getattr(self, actionname)
            assert isinstance(action, QtWidgets.QAction)
            action.triggered.connect(self.onShowHideProjectWindow)
            action.setEnabled(False)
        self.actionRecent_projects.setMenu(QtWidgets.QMenu())
        self.loadRecentFileList()

    def onShowHideProjectWindow(self, checked: bool):
        if self.project is None:
            return
        for wi in self.windowinfo:
            if self.sender() is getattr(self, wi.action):
                window = getattr(self, wi.attribute)
                window.parent().setVisible(checked)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.closeProject()
        event.accept()

    def onSubWindowHidden(self, widget: QtWidgets.QWidget):
        subwindow = self.sender()
        assert isinstance(subwindow, ClosableMdiSubWindow)
        for wi in self.windowinfo:
            if widget is getattr(self, wi.attribute):
                action = getattr(self, wi.action)
                action.blockSignals(True)
                action.setChecked(False)
                action.blockSignals(False)

    def saveProject(self) -> bool:
        if not self.windowFilePath():
            return self.saveProjectAs()
        else:
            self.project.save(self.windowFilePath())
            return True

    def newProject(self):
        self.closeProject()
        filename, filter_ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save the new CPT project to', '',
            'CPT4 project files (*.cpt4);;Old-style CPT project files (*.cpt *.cpt2);;All files (*)',
            'CPT4 project files (*.cpt4)')
        if not filename:
            return
        if not filename.lower().endswith('.cpt4'):
            filename = filename + '.cpt4'
        self.project = Processing(filename)
        self.createProjectWindows()
        self.setWindowFilePath(self.project.settings.filename)
        self.setWindowTitle(f'CREDO Processing Tool - {self.project.settings.filename}')
        self.addNewRecentFile(filename)

    def addNewRecentFile(self, filename):
        logger.debug(
            f'Adding new file to the recents list: {filename}. '
            f'Current actions: {[a.text() for a in self.actionRecent_projects.menu().actions()]}')
        for action in self.actionRecent_projects.menu().actions():
            if action.toolTip() == filename:
                logger.debug(f'Removing already existing action with file name {action.toolTip()}')
                self.actionRecent_projects.menu().removeAction(action)
        a = QtWidgets.QAction(self)
        a.setText(os.path.split(filename)[-1])
        a.setToolTip(filename)
        a.triggered.connect(self.loadRecentFile)
        try:
            self.actionRecent_projects.menu().insertAction(self.actionRecent_projects.menu().actions()[0], a)
        except IndexError:
            self.actionRecent_projects.menu().addAction(a)
        logger.debug(
            f'Added new file to the recents list: {filename}. '
            f'Current actions: {[a.text() for a in self.actionRecent_projects.menu().actions()]}')
        self.saveRecentFileList()

    @QtCore.pyqtSlot()
    def openProject(self, filename: Optional[str] = None):
        if filename is None:
            filename, filter_ = QtWidgets.QFileDialog.getOpenFileName(
                self, 'Open a CPT project file', '',
                'CPT4 project files (*.cpt4);;Old-style CPT project files (*.cpt *.cpt2);;All files (*)',
                'CPT4 project files (*.cpt4)')
            if not filename:
                return
        logger.debug(f'Loading project from file {filename}')
        self.project = Processing.fromFile(filename)
        logger.debug(f'Loaded project from file {filename}')
        self.setWindowFilePath(filename)
        self.setWindowTitle(f'CREDO Processing Tool - {self.project.settings.filename}')
        self.createProjectWindows()
        logger.debug('Created project windows.')
        self.loadWindowGeometry()
        logger.debug('Loaded window geometry.')
        self.addNewRecentFile(filename)

    def saveProjectAs(self) -> bool:  # True if saved successfully
        filename, filter_ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Select a file to save the project to', '',
            'CPT4 project files (*.cpt4);;All files (*)',
            'CPT4 project files (*.cpt4)')
        if not filename:
            return False
        self.setWindowFilePath(filename)
        return self.saveProject()

    def closeProject(self):
        if self.project is None:
            return
        self.saveWindowGeometry()
        self.destroyProjectWindows()
        self.project.deleteLater()
        self.project = None
        self.setWindowFilePath('')

    def createProjectWindows(self):
        logger.debug('CreateProjectWindows called')
        self.destroyProjectWindows()
        logger.debug('Now creating project windows')
        for wi in self.windowinfo:
            logger.debug(f'Creating project window type {wi.attribute}')
            assert not (hasattr(self, wi.attribute) and (getattr(self, wi.attribute) is not None))
            widget = wi.windowclass(self.project, self)
            setattr(self, wi.attribute, widget)
            sw = ClosableMdiSubWindow()
            sw.setWidget(widget)
            self.mdiArea.addSubWindow(sw)
            widget.destroyed.connect(self.onWidgetDestroyed)
            sw.setWindowIcon(widget.windowIcon())
            sw.close()
            sw.hidden.connect(self.onSubWindowHidden)
            action = getattr(self, wi.action)
            assert isinstance(action, QtWidgets.QAction)
            action.setEnabled(True)
            action.setChecked(False)
            logger.debug(f'Created project window type {wi.attribute}')
        self.actionProject_window.setChecked(True)
        self.projectwindow.showNormal()

    def destroyProjectWindows(self):
        logger.debug('Destroying project windows')
        for wi in self.windowinfo:
            widget = getattr(self, wi.attribute)
            if widget is not None:
                logger.debug(f'Removing an MDI subwindow for widget {widget=}')
                self.mdiArea.removeSubWindow(widget.parent())
                widget.destroy(True, True)
                widget.deleteLater()
            action = getattr(self, wi.action)
            assert isinstance(action, QtWidgets.QAction)
            action.blockSignals(True)
            action.setEnabled(False)
            action.setChecked(False)
            action.blockSignals(False)
            setattr(self, wi.attribute, None)

        for widget in self.viewwindows.values():
            self.mdiArea.removeSubWindow(widget.parent())
            widget.destroy(True, True)
            widget.deleteLater()
        self.viewwindows = {}
        logger.debug('Destroyed all project windows.')

    def createViewWindow(self, windowclass: Type[ResultViewWindow], items: List[Tuple[str, str]],
                         geometry: Optional[bytes] = None) -> ResultViewWindow:
        items_str = '([' + ', '.join([f'({sn}, {dk})' for sn, dk in items]) + '])'
        handlestring = windowclass.__name__ + items_str
        if handlestring not in self.viewwindows:
            self.viewwindows[handlestring] = windowclass(
                project=self.project, mainwindow=self, resultitems=items,
                closable=True)
            subwindow = self.mdiArea.addSubWindow(self.viewwindows[handlestring])
            self.viewwindows[handlestring].setObjectName(
                self.viewwindows[handlestring].objectName() + f'__{time.monotonic()}')
            self.viewwindows[handlestring].destroyed.connect(self.onWidgetDestroyed)
            subwindow.setWindowIcon(self.viewwindows[handlestring].windowIcon())
        self.viewwindows[handlestring].raise_()
        self.viewwindows[handlestring].showNormal()
        if geometry is not None:
            self.viewwindows[handlestring].restoreGeometry(geometry)
        return self.viewwindows[handlestring]

    def onWidgetDestroyed(self, object: QtWidgets.QWidget):
        for key in list(self.viewwindows):
            try:
                self.viewwindows[key].objectName()
            except RuntimeError:
                logger.debug(
                    f'Removing {key} from the view windows dictionary '
                    f'because the wrapped C/C++ object has been deleted')
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

    def saveWindowGeometry(self):
        with self.project.settings.h5io.writer('cpt4gui') as grp:
            wg = grp.require_group('windows')
            for key in wg:
                del wg[key]
            for wi in self.windowinfo:
                g = wg.create_group(f'M:{wi.attribute}')
                subwindow = getattr(self, wi.attribute).parent()
                assert isinstance(subwindow, QtWidgets.QMdiSubWindow)
                g.attrs['geometry'] = subwindow.saveGeometry()
                g.attrs['minimized'] = subwindow.isMinimized()
                g.attrs['maximized'] = subwindow.isMaximized()
                g.attrs['hidden'] = subwindow.isHidden()
                g.attrs['fullscreen'] = subwindow.isFullScreen()
                g.attrs['shaded'] = subwindow.isShaded()
            for name, vw in self.viewwindows.items():
                g = wg.create_group(f'R:{name}')
                subwindow = vw.parent()
                assert isinstance(subwindow, QtWidgets.QMdiSubWindow)
                g.attrs['geometry'] = subwindow.saveGeometry()
                g.attrs['minimized'] = subwindow.isMinimized()
                g.attrs['maximized'] = subwindow.isMaximized()
                g.attrs['hidden'] = subwindow.isHidden()
                g.attrs['fullscreen'] = subwindow.isFullScreen()
                g.attrs['shaded'] = subwindow.isShaded()
                g.attrs['class'] = type(vw).__name__
                g.create_dataset('items', data=[(sn.encode('utf-8'), dk.encode('utf-8')) for sn, dk in vw.resultitems])

    def loadWindowGeometry(self):
        logger.debug('Loading window geometry')
        windowstate = {}
        resultviewwindows = {}
        try:
            # first load all state information, avoid hogging the H5 file
            with self.project.settings.h5io.reader('cpt4gui/windows') as grp:
                # load state information of basic windows
                for wi in self.windowinfo:
                    logger.debug(f'{wi}')
                    try:
                        label = f'M:{wi.attribute}'
                        windowstate[wi.attribute] = {
                            'geometry': bytes(grp[label].attrs['geometry']),
                            'hidden': grp[label].attrs['hidden'],
                            'shaded': grp[label].attrs['shaded'],
                            'minimized': grp[label].attrs['minimized'],
                            'maximized': grp[label].attrs['maximized'],
                            'fullscreen': grp[label].attrs['fullscreen'],
                            'basewindow': True
                        }
                    except (KeyError, TypeError):
                        logger.warning(f'Cannot find geometry for window {label}')
                    else:
                        logger.debug(f'Geometry loaded for window {wi=}')
                for key in [k for k in grp if k.startswith('R:')]:
                    try:
                        windowclass = \
                            [c for c in ResultViewWindow.__subclasses__() if c.__name__ == grp[key].attrs['class']][0]
                    except IndexError:
                        logger.warning(f'Unsupported window class: {grp[key].attrs["class"]}')
                        continue
                    items = grp[key]['items']
                    resultviewwindows[key] = {
                        'class': windowclass,
                        'items': [
                            (items[row, 0].decode('utf-8'), items[row, 1].decode('utf-8'))
                            for row in range(items.shape[0])]
                    }
                    windowstate[key] = {
                        'geometry': bytes(grp[key].attrs['geometry']),
                        'hidden': grp[key].attrs['hidden'],
                        'shaded': grp[key].attrs['shaded'],
                        'minimized': grp[key].attrs['minimized'],
                        'maximized': grp[key].attrs['maximized'],
                        'fullscreen': grp[key].attrs['fullscreen'],
                        'basewindow': False
                    }
        except KeyError:
            logger.debug('Cannot load geometry information from H5 file.')
            return
        for label in windowstate:
            logger.debug(f'Updating window state for window {label}')
            if windowstate[label]['basewindow']:
                win = getattr(self, label)
            else:
                # create the result view window
                win = self.createViewWindow(resultviewwindows[label]['class'], resultviewwindows[label]['items'])
            # get the subwindow
            subwindow: QtWidgets.QMdiSubWindow = win.parent()
            # restore the size and position of the subwindow
            logger.debug(f'Restoring geometry of window {label}')
            subwindow.restoreGeometry(windowstate[label]['geometry'])
            # set window state: normal, minimized, maximized, full screen, shaded etc.
            logger.debug(f'Window {label} is hidden: {windowstate[label]["hidden"]}')
            subwindow.setHidden(windowstate[label]['hidden'])
            if windowstate[label]['shaded']:
                logger.debug(f'Shading window {label}')
                subwindow.showShaded()
            elif windowstate[label]['minimized']:
                logger.debug(f'Minimizing window {label}')
                subwindow.showMinimized()
            elif windowstate[label]['maximized']:
                logger.debug(f'Maximizing window {label}')
                subwindow.showMaximized()
            elif windowstate[label]['fullscreen']:
                logger.debug(f'Setting window {label} full screen')
                subwindow.showFullScreen()
            elif not windowstate[label]['hidden']:
                logger.debug(f'Showing window {label} as normal')
                subwindow.showNormal()
            # update the state of the corresponding action
            try:
                wi = [wi_ for wi_ in self.windowinfo if wi_.attribute == label][0]
            except IndexError:
                assert not windowstate[label]['basewindow']
            else:
                action: QtWidgets.QAction = getattr(self, wi.action)
                action.blockSignals(True)
                action.setChecked(not windowstate[label]['hidden'])
                action.blockSignals(False)

    def loadRecentFileList(self):
        logger.debug(
            f'Loading recent file list. List is now: '
            f'{[a.toolTip() for a in self.actionRecent_projects.menu().actions()]}')
        self.actionRecent_projects.menu().clear()
        try:
            with open(os.path.join(appdirs.user_config_dir('cct'), 'cpt4.recents'), 'rt') as f:
                for line in f:
                    if os.path.isfile(line.strip()):
                        logger.debug(f'Adding action for file {line.strip()}')
                        action = QtWidgets.QAction(self)
                        action.setText(os.path.split(line.strip())[-1])
                        action.setToolTip(line.strip())
                        action.triggered.connect(self.loadRecentFile)
                        self.actionRecent_projects.menu().addAction(action)
                    else:
                        logger.warning(f'Ignoring unavailable file: {line.strip()}')
        except FileNotFoundError:
            return
        logger.debug(
            f'Loaded recent file list. List is now: '
            f'{[a.toolTip() for a in self.actionRecent_projects.menu().actions()]}')

    def saveRecentFileList(self):
        logger.debug('Saving recent files list.')
        os.makedirs(appdirs.user_config_dir('cct'), exist_ok=True)
        with open(os.path.join(appdirs.user_config_dir('cct'), 'cpt4.recents'), 'wt') as f:
            for action in self.actionRecent_projects.menu().actions():
                logger.debug(f'File name: {action.toolTip()}')
                f.write(action.toolTip() + '\n')

    def loadRecentFile(self):
        action = self.sender()
        assert isinstance(action, QtWidgets.QAction)
        filename = action.toolTip()
        logger.debug(f'Loading recent file: {action.toolTip()}')
        self.openProject(filename)
