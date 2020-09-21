import logging
import time
from typing import Dict, Optional

import pkg_resources
from PyQt5 import QtWidgets, QtGui, QtCore

from .devicestatus import DeviceStatus
from .indicators.accounting import AccountingIndicator
from .indicators.beamstop import BeamstopIndicator
from .indicators.lastfsn import LastFSNIndicator
from .indicators.shutter import ShutterIndicator
from .logviewer_text import LogViewerText
from .mainwindow_ui import Ui_MainWindow
from .scripting import Scripting
from ..devices.connectioneditor.connectioneditor import ConnectionEditor
from ..devices.genix.genix import GeniXTool
from ..devices.haakephoenix.haakephoenix import HaakePhoenixDevice
from ..devices.motors.motorview import MotorView
from ..devices.pilatus.pilatus import PilatusDetector
from ..listing.headerview import HeaderView
from ..listing.scanview import ScanViewer
from ..measurement.simpleexposure.simpleexposure import SimpleExposure
from ..setup.calibrants.calibrants import Calibrants
from ..setup.calibration.calibration import Calibration
from ..setup.geometry.geometry import GeometryEditor
from ..setup.projectmanager.projectmanager import ProjectManager
from ..setup.samples.sampleeditor import SampleEditor
from ..setup.usermanager.passwordchange import PasswordChange
from ..setup.usermanager.usermanager import UserManager
from ..tools.capillarysizer import CapillarySizer
from ..tools.maskeditor.maskeditor import MaskEditor
from ..tools.samplepositionchecker import SamplePositionChecker
from ..utils.plotimage import PlotImage
from ..utils.window import WindowRequiresDevices
from ...core2.instrument.instrument import Instrument
from ...core2.instrument.components.interpreter import ParsingError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    logViewer: LogViewerText
    instrument: Instrument
    plotimage: PlotImage
    lastfsnindicator: LastFSNIndicator
    accountingindicator: AccountingIndicator
    beamstopindicator: BeamstopIndicator
    shutterindicator: ShutterIndicator
    scripting: Scripting

    _action2windowclass = {
        'actionX_ray_source': GeniXTool,
        'actionMotors': MotorView,
        'actionSample_editor': SampleEditor,
        'actionGeometry_editor': GeometryEditor,
        'actionCalibrantsDB': Calibrants,
        'actionCalibration': Calibration,
        'actionSamplePositionChecker': SamplePositionChecker,
        'actionView_scans': ScanViewer,
        'actionMask_editor': MaskEditor,
        'actionUser_management': UserManager,
        'actionChange_password': PasswordChange,
        'actionProject_management': ProjectManager,
        'actionCapillary_sizing': CapillarySizer,
        'actionDevice_connections': ConnectionEditor,
        'actionSingle_exposure': SimpleExposure,
        'actionDetector': PilatusDetector,
        'actionTemperature_stage': HaakePhoenixDevice,
        'actionView_images_and_curves': HeaderView,
        'actionData_reduction': HeaderView,

    }
    _windows: Dict[str, QtWidgets.QWidget]

    def __init__(self, **kwargs):
        super().__init__(kwargs['parent'] if 'parent' in kwargs else None)
        self.instrument = kwargs['instrument']
        self.instrument.shutdown.connect(self.close)
        self.instrument.interpreter.scriptstarted.connect(self.onInterpreterStarted)
        self.instrument.interpreter.scriptfinished.connect(self.onInterpreterFinished)
        self.instrument.interpreter.progress.connect(self.onInterpreterProgress)
        self.instrument.interpreter.message.connect(self.onInterpreterMessage)
        self.instrument.devicemanager.deviceConnected.connect(self.onDeviceConnected)
        self._windows = {}
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        rootlogger = logging.root
        self.logViewer = LogViewerText(parent=self.centralwidget)
        self.logHorizontalLayout.addWidget(self.logViewer)
        rootlogger.addHandler(self.logViewer)
        self.actionQuit.triggered.connect(self.close)
        self.progressBar.setVisible(False)
        self.plotimage = PlotImage(self.patternTab)
        self.patternTab.setLayout(QtWidgets.QVBoxLayout())
        self.patternTab.layout().addWidget(self.plotimage)
        for actionname, windowclass in self._action2windowclass.items():
            action = getattr(self, actionname)
            assert isinstance(action, QtWidgets.QAction)
            action.triggered.connect(self.onActionTriggered)
        self.setWindowTitle(
            f'Credo Control Tool v{pkg_resources.get_distribution("cct").version} User: {self.instrument.auth.username()}')
        self.accountingindicator = AccountingIndicator(parent=self.centralwidget)
        self.indicatorHorizontalLayout.addWidget(self.accountingindicator)
        self.lastfsnindicator = LastFSNIndicator(parent=self.centralwidget)
        self.indicatorHorizontalLayout.addWidget(self.lastfsnindicator)
        self.beamstopindicator = BeamstopIndicator(parent=self.centralwidget)
        self.indicatorHorizontalLayout.addWidget(self.beamstopindicator)
        self.shutterindicator = ShutterIndicator(parent=self.centralwidget)
        self.indicatorHorizontalLayout.addWidget(self.shutterindicator)
        self.indicatorHorizontalLayout.addStretch(1)
        self.scripting = Scripting(mainwindow=self, instrument=self.instrument)
        self.scriptingTab.setLayout(QtWidgets.QVBoxLayout())
        self.scriptingTab.layout().addWidget(self.scripting)
        self.executePushButton.clicked.connect(self.onExecutePushed)

    def onActionTriggered(self, toggled: bool):
        action = self.sender()
        windowclass = self._action2windowclass[action.objectName()]
        logger.debug(f'Window class: {windowclass}')
        assert issubclass(windowclass, QtWidgets.QWidget)
        try:
            self._windows[windowclass.__name__].show()
            self._windows[windowclass.__name__].raise_()
            self._windows[windowclass.__name__].setFocus()
        except KeyError:
            assert issubclass(windowclass, WindowRequiresDevices)
            assert issubclass(windowclass, QtWidgets.QWidget)
            self.addSubWindow(windowclass, singleton=True)

    def addSubWindow(self, windowclass, singleton: bool = True) -> Optional[WindowRequiresDevices]:
        if windowclass.canOpen(self.instrument):
            if singleton and windowclass.__name__ in self._windows:
                raise ValueError(f'Window class {windowclass} has already an active instance.')
            if not singleton:
                objectname = windowclass.__name__ + str(time.monotonic())
            else:
                objectname = windowclass.__name__
            w = windowclass(parent=None, instrument=self.instrument, mainwindow=self)
            w.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
            w.destroyed.connect(self.onWindowDestroyed)
            w.setObjectName(objectname)
            self._windows[objectname] = w
            w.show()
            w.raise_()
            w.setFocus()
            return w
        return None

    def onWindowDestroyed(self, window: QtWidgets.QWidget):
        logger.debug(f'Window with object name {window.objectName()} destroyed.')
        del self._windows[window.objectName()]

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        logger.debug('closeEvent in Main window')
        if not self.instrument.running:
            logger.debug('Instrument is not running, closing all windows')
            for name in self._windows:
                self._windows[name].close()
            logger.debug('All windows closed, accepting close event.')
            self.instrument.config.save()
            event.accept()
        elif not self.instrument.stopping:
            logger.debug('Instrument is running.')
            event.ignore()
            result = QtWidgets.QMessageBox.question(self, 'Confirm quit', 'Do you really want to quit CCT?',
                                                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                                    QtWidgets.QMessageBox.No)
            if result == QtWidgets.QMessageBox.Yes:
                logger.debug('Stopping instrument')
                self.instrument.stop()
        logger.debug('Exiting closeEvent')

    def onInterpreterFinished(self, success: bool, message: str):
        self.commandLineEdit.setEnabled(True)
        self.progressBar.setVisible(False)
        self.executePushButton.setEnabled(True)

    def onInterpreterStarted(self):
        self.commandLineEdit.setEnabled(False)
        self.executePushButton.setEnabled(False)

    def onInterpreterProgress(self, message: str, current: int, total: int):
        self.progressBar.setRange(0, total)
        self.progressBar.setValue(current)
        self.progressBar.setFormat(message)
        self.progressBar.setVisible(True)

    def onInterpreterMessage(self, message: str):
        self.statusBar().showMessage(message)

    def onDeviceConnected(self, device: str):
        ds = DeviceStatus(device=self.instrument.devicemanager[device])
        self.deviceStatusBarLayout.insertWidget(self.deviceStatusBarLayout.count() - 1, ds)

    def onExecutePushed(self):
        if self.executePushButton.text() == 'Stop':
            self.instrument.interpreter.stop()
        else:
            try:
                self.instrument.interpreter.parseScript(self.commandLineEdit.text())
            except ParsingError:
                pal = self.commandLineEdit.palette()
                pal.setColor(pal.Window, QtCore.Qt.red)
                self.commandLineEdit.setPalette(pal)
                return
