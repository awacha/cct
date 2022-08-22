import collections
import logging
import os
import time
from typing import Optional, Dict, Final, List, Tuple, Type

import appdirs
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

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
from ..utils.filebrowsers import getOpenFile, getSaveFile

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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

    @Slot(bool)
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

    @Slot(QtWidgets.QWidget)
    def onSubWindowHidden(self, widget: QtWidgets.QWidget):
        subwindow = self.sender()
        assert isinstance(subwindow, ClosableMdiSubWindow)
        for wi in self.windowinfo:
            if widget is getattr(self, wi.attribute):
                action = getattr(self, wi.action)
                action.blockSignals(True)
                action.setChecked(False)
                action.blockSignals(False)

    @Slot()
    def saveProject(self) -> bool:
        if not self.windowFilePath():
            return self.saveProjectAs()
        else:
            self.project.save(self.windowFilePath())
            return True

    @Slot()
    def newProject(self):
        self.closeProject()
        filename = getSaveFile(
            self, 'Save the new CPT project to', '',
            'CPT4 project files (*.cpt4);;Old-style CPT project files (*.cpt *.cpt2);;All files (*)', '.cpt4')
        if not filename:
            return
        self.project = Processing(filename)
        self.createProjectWindows()
        self.setWindowFilePath(self.project.settings.filename)
        self.setWindowTitle(f'CREDO Processing Tool - {self.project.settings.filename}')
        self.addNewRecentFile(filename)

    @Slot(str)
    def addNewRecentFile(self, filename: str):
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

    @Slot()
    @Slot(str)
    def openProject(self, filename: Optional[str] = None):
        if filename is None:
            filename = getOpenFile(
                self, 'Open a CPT project file...', '',
                'CPT4 project files (*.cpt4);;Old-style CPT project files (*.cpt *.cpt2);;All files (*)')
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

    @Slot()
    def saveProjectAs(self) -> bool:  # True if saved successfully
        filename = getSaveFile(self, 'Save the project to...', '', 'CPT4 project files (*.cpt4);;All files (*)', '.cpt4')
        if not filename:
            return False
        self.setWindowFilePath(filename)
        return self.saveProject()

    @Slot()
    def closeProject(self):
        if self.project is None:
            return
        self.saveWindowGeometry()
        self.destroyProjectWindows()
        self.project.deleteLater()
        self.project = None
        self.setWindowFilePath('')

    @Slot()
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

    @Slot()
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

    def addMDISubWindow(self, widget: QtWidgets.QWidget):
        subwindow = QtWidgets.QMdiSubWindow()
        subwindow.setWidget(widget)
        self.mdiArea.addSubWindow(subwindow)
        subwindow.setWindowIcon(widget.windowIcon())
        widget.destroyed.connect(self.onWidgetDestroyed)
        subwindow.show()

    def createViewWindow(self, windowclass: Type[ResultViewWindow], items: List[Tuple[str, str]],
                         geometry: Optional[bytes] = None) -> ResultViewWindow:
        items_str = '([' + ', '.join([f'({sn}, {dk})' for sn, dk in items]) + '])'
        handlestring = windowclass.__name__ + items_str
        if handlestring not in self.viewwindows:
            self.viewwindows[handlestring] = windowclass(
                project=self.project, mainwindow=self, resultitems=items,
                closable=True)
            self.addMDISubWindow(self.viewwindows[handlestring])
            self.viewwindows[handlestring].setObjectName(
                self.viewwindows[handlestring].objectName() + f'__{time.monotonic()}')
        self.viewwindows[handlestring].parent().raise_()
        self.viewwindows[handlestring].parent().showNormal()
        if geometry is not None:
            self.viewwindows[handlestring].parent().restoreGeometry(geometry)
        return self.viewwindows[handlestring]

    @Slot(QtCore.QObject)
    def onWidgetDestroyed(self, object: QtCore.QObject):
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
        else:
            logger.warning(f'Widget {object.objectName()=} destroyed but could not remove')
        for subwin in self.mdiArea.subWindowList():
            try:
                if subwin.widget() is not None:
                    subwin.widget().objectName()
            except RuntimeError:
                logger.debug(f'Destroying subwindow {subwin.objectName()}, since its child widget is no longer '
                             f'available (wrapped C/C++ object has been deleted)')
                subwin.setWidget(None)
                subwin.destroy(True, True)
                continue
            if (subwin.widget() is None) or (subwin.widget()):
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
                g.attrs['x'] = subwindow.x()
                g.attrs['y'] = subwindow.y()
                g.attrs['width'] = subwindow.width()
                g.attrs['height'] = subwindow.height()
            for name, vw in self.viewwindows.items():
                g = wg.create_group(f'R:{name}')
                subwindow = vw.parent()
                if subwindow.isHidden():
                    # do not save hidden subwindows
                    del wg[f'R:{name}']
                assert isinstance(subwindow, QtWidgets.QMdiSubWindow)
                g.attrs['geometry'] = subwindow.saveGeometry()
                g.attrs['minimized'] = subwindow.isMinimized()
                g.attrs['maximized'] = subwindow.isMaximized()
                g.attrs['hidden'] = subwindow.isHidden()
                g.attrs['fullscreen'] = subwindow.isFullScreen()
                g.attrs['shaded'] = subwindow.isShaded()
                g.attrs['class'] = type(vw).__name__
                g.attrs['x'] = subwindow.x()
                g.attrs['y'] = subwindow.y()
                g.attrs['width'] = subwindow.width()
                g.attrs['height'] = subwindow.height()
                g.create_dataset('items', data=[(sn.encode('utf-8'), dk.encode('utf-8')) for sn, dk in vw.resultitems])
        logger.info('Saved window geometries')

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
                            'basewindow': True,
                            'x': grp[label].attrs['x'] if 'x' in grp[label].attrs else None,
                            'y': grp[label].attrs['y'] if 'y' in grp[label].attrs else None,
                            'width': grp[label].attrs['width'] if 'width' in grp[label].attrs else None,
                            'height': grp[label].attrs['height'] if 'height' in grp[label].attrs else None,
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
                        'basewindow': False,
                        'x': grp[label].attrs['x'] if 'x' in grp[label].attrs else None,
                        'y': grp[label].attrs['y'] if 'y' in grp[label].attrs else None,
                        'width': grp[label].attrs['width'] if 'width' in grp[label].attrs else None,
                        'height': grp[label].attrs['height'] if 'height' in grp[label].attrs else None,
                    }
        except KeyError:
            logger.debug('Cannot load geometry information from H5 file.')
            return
        for label in windowstate:
            logger.debug(f'Updating window state for window {label}')
            if windowstate[label]['basewindow']:
                win = getattr(self, label)
            elif not windowstate[label]['hidden']:
                # create the result view window. Do not create hidden result windows!
                win = self.createViewWindow(resultviewwindows[label]['class'], resultviewwindows[label]['items'])
            else:
                # do nothing, hidden result windows are not created because they cannot be re-shown from the GUI
                continue
            # get the subwindow
            subwindow: QtWidgets.QMdiSubWindow = win.parent()
            # set window state: normal, minimized, maximized, full screen, shaded etc.
            if windowstate[label]['hidden']:
                logger.warning(f'Window {label} is hidden: {windowstate[label]["hidden"]}')
                subwindow.setHidden(windowstate[label]['hidden'])
            else:
                subwindow.show()
            if windowstate[label]['shaded']:
                logger.warning(f'Shading window {label}')
                subwindow.showShaded()
            elif windowstate[label]['minimized']:
                logger.warning(f'Minimizing window {label}')
                subwindow.showMinimized()
            elif windowstate[label]['maximized']:
                logger.warning(f'Maximizing window {label}')
                subwindow.showMaximized()
            elif windowstate[label]['fullscreen']:
                logger.warning(f'Setting window {label} full screen')
                subwindow.showFullScreen()
            elif not windowstate[label]['hidden']:
                logger.info(f'Showing window {label} as normal')
                subwindow.showNormal()
            # restore the size and position of the subwindow
            if (windowstate[label]['x'] is None) and (windowstate[label]['y'] is None) and (windowstate[label]['width'] is None) and (windowstate[label]['height'] is None):
                logger.error(f'Restoring geometry of window {label} FROM GEOMETRY')
                subwindow.restoreGeometry(windowstate[label]['geometry'])
            else:
                logger.debug(f'Restoring geometry of window {label} FROM X, Y, WIDTH, HEIGHT')
                if (windowstate[label]['x'] is not None) and (windowstate[label]['y'] is not None):
                    subwindow.move(windowstate[label]['x'], windowstate[label]['y'])
                    logger.debug(f'x={windowstate[label]["x"]}, y={windowstate[label]["y"]}')
                if (windowstate[label]['width'] is not None) and (windowstate[label]['height'] is not None):
                    subwindow.resize(windowstate[label]['width'], windowstate[label]['height'])
                    logger.debug(f'width={windowstate[label]["width"]}, height={windowstate[label]["height"]}')
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

    @Slot()
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

    @Slot()
    def loadRecentFile(self):
        action = self.sender()
        assert isinstance(action, QtWidgets.QAction)
        filename = action.toolTip()
        logger.debug(f'Loading recent file: {action.toolTip()}')
        self.openProject(filename)
