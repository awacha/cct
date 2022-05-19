import logging
import time
from typing import Dict, Optional, Union, List

import pkg_resources
from PyQt5 import QtWidgets, QtGui, QtCore

from .devicestatus import DeviceStatus
from .devicevariablemeasurement import DeviceVariableMeasurement
from .indicators.accounting import AccountingIndicator
from .indicators.beamstop import BeamstopIndicator
from .indicators.lastfsn import LastFSNIndicator
from .indicators.plotindicator import PlotIndicator
from .indicators.shutter import ShutterIndicator
from .logviewer_text import LogViewerText
from .mainwindow_ui import Ui_MainWindow
from .scripting import Scripting
from ..devices.connectioneditor.connectioneditor import ConnectionEditor
from ..devices.genix.genix import GeniXTool
from ..devices.haakephoenix.haakephoenix import HaakePhoenixDevice
from ..devices.illumination.schottKL2500LED import SchottKL2500LEDUI
from ..devices.motors.motorview import MotorView
from ..devices.peristalticpump.leadfluid import LeadFluid_BT100S
from ..devices.pilatus.pilatus import PilatusDetectorUI
from ..devices.thermometer.se521 import SE521Window
from ..devices.ups.keen800 import Keen80UPS
from ..devices.ups.tecnoware import TecnowareUPS
from ..listing.headerview import HeaderView
from ..listing.scanview import ScanViewer
from ..measurement.monitor import MonitorMeasurement
from ..measurement.scan.scan import ScanMeasurement
from ..measurement.simpleexposure.simpleexposure import SimpleExposure
from ..measurement.transmission import TransmissionUi
from ..setup.calibrants.calibrants import Calibrants
from ..setup.calibration.calibration import Calibration
from ..setup.deviceloggers.devicelogmanager import DeviceLogManagerUI
from ..setup.geometry.geometry import GeometryEditor
from ..setup.notifier.notifier import NotifierSetup
from ..setup.projectmanager.projectmanager import ProjectManager
from ..setup.samples.sampleeditor import SampleEditor
from ..setup.usermanager.passwordchange import PasswordChange
from ..setup.usermanager.usermanager import UserManager
from ..tools.capillarysizer import CapillarySizer
from ..tools.maskeditor.maskeditor import MaskEditor
from ..tools.samplepositionchecker import SamplePositionChecker
from ..tools.sensors.sensors import SensorsWindow
from ..utils.anisotropy import AnisotropyEvaluator
from ..utils.plotcurve import PlotCurve
from ..utils.plotimage import PlotImage
from ..utils.window import WindowRequiresDevices
from ...core2.dataclasses import Exposure, Curve
from ...core2.instrument.components.interpreter import ParsingError
from ...core2.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    logViewer: LogViewerText
    instrument: Instrument
    plotimage: PlotImage
    plotcurve: PlotCurve
    lastfsnindicator: LastFSNIndicator
    accountingindicator: AccountingIndicator
    beamstopindicator: BeamstopIndicator
    shutterindicator: ShutterIndicator
    plotindicator: PlotIndicator
    scripting: Scripting
    devicevariablemeasurement: DeviceVariableMeasurement

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
        'actionDetector': PilatusDetectorUI,
        'actionTemperature_stage': HaakePhoenixDevice,
        'actionView_images_and_curves': HeaderView,
        'actionData_reduction': HeaderView,
        'actionScan': ScanMeasurement,
        'actionTransmission': TransmissionUi,
        'actionThermometer': SE521Window,
        'actionSensors': SensorsWindow,
        'actionBeam_Monitor': MonitorMeasurement,
        'actionKeen800UPS': Keen80UPS,
        'actionPeristaltic_pump': LeadFluid_BT100S,
        'actionTecnowareUPS': TecnowareUPS,  # ToDo: group similar instruments
        'actionNotification': NotifierSetup,
        'actionDevice_loggers': DeviceLogManagerUI,
        'actionSchott_KL2500LED': SchottKL2500LEDUI,
        'actionAnisotropy': AnisotropyEvaluator,

    }
    _windows: Dict[str, QtWidgets.QWidget]
    _devicestatuswidgets: List[DeviceStatus]

    def __init__(self, **kwargs):
        self._devicestatuswidgets = []
        super().__init__(kwargs['parent'] if 'parent' in kwargs else None)
        self.instrument = kwargs['instrument']
        self.instrument.panicAcknowledged.connect(self.onPanicAcknowledged)
        self.instrument.shutdown.connect(self.close)
        self.instrument.interpreter.scriptstarted.connect(self.onInterpreterStarted)
        self.instrument.interpreter.scriptfinished.connect(self.onInterpreterFinished)
        self.instrument.interpreter.progress.connect(self.onInterpreterProgress)
        self.instrument.interpreter.message.connect(self.onInterpreterMessage)
        self.instrument.devicemanager.deviceAdded.connect(self.onDeviceAdded)
        self.instrument.devicemanager.deviceRemoved.connect(self.onDeviceRemoved)
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
        self.plotcurve = PlotCurve(self.curveTab)
        self.curveTab.setLayout(QtWidgets.QVBoxLayout())
        self.curveTab.layout().addWidget(self.plotcurve)
        for actionname, windowclass in self._action2windowclass.items():
            action = getattr(self, actionname)
            assert isinstance(action, QtWidgets.QAction)
            action.triggered.connect(self.onActionTriggered)
        self.setWindowTitle(
            f'Credo Control Tool v{pkg_resources.get_distribution("cct").version} User: {self.instrument.auth.username()}')
        self.accountingindicator = AccountingIndicator(parent=self.centralwidget, instrument=self.instrument,
                                                       mainwindow=self)
        self.indicatorHorizontalLayout.addWidget(self.accountingindicator)
        self.lastfsnindicator = LastFSNIndicator(parent=self.centralwidget, instrument=self.instrument, mainwindow=self)
        self.indicatorHorizontalLayout.addWidget(self.lastfsnindicator)
        self.beamstopindicator = BeamstopIndicator(parent=self.centralwidget, instrument=self.instrument,
                                                   mainwindow=self)
        self.indicatorHorizontalLayout.addWidget(self.beamstopindicator)
        self.shutterindicator = ShutterIndicator(parent=self.centralwidget, instrument=self.instrument, mainwindow=self)
        self.indicatorHorizontalLayout.addWidget(self.shutterindicator)
        self.plotindicator = PlotIndicator(parent=self.centralwidget, instrument=self.instrument, mainwindow=self)
        self.indicatorHorizontalLayout.addWidget(self.plotindicator)
        self.indicatorHorizontalLayout.addStretch(1)
        self.actionScript.triggered.connect(self.onScriptTriggered)
        self.actionLogbook.triggered.connect(self.onLogTriggered)
        self.scripting = Scripting(mainwindow=self, instrument=self.instrument)
        self.scriptingTab.setLayout(QtWidgets.QVBoxLayout())
        self.scriptingTab.layout().addWidget(self.scripting)
        self.executePushButton.clicked.connect(self.onExecutePushed)
        self.actionSave_settings.triggered.connect(self.saveSettings)
        self.panicPushButton.clicked.connect(self.onPanicClicked)
        for dev in self.instrument.devicemanager:
            self.onDeviceAdded(dev.name)
        self.devicevariablemeasurement = DeviceVariableMeasurement(mainwindow=self, instrument=self.instrument)
        self.deviceStatusTab.setLayout(QtWidgets.QVBoxLayout())
        self.deviceStatusTab.layout().addWidget(self.devicevariablemeasurement)

    def saveSettings(self):
        self.instrument.saveConfig()

    def onPanicClicked(self):
        self.instrument.panic('User clicked on the panic button')

    def onPanicAcknowledged(self):
        QtWidgets.QMessageBox.critical(
            self, 'Panic',
            f'Panic occurred, the instrument has been shut down. The program will exit. '
            f'Reason of the panic: {self.instrument.panicreason}')

    def onScriptTriggered(self):
        self.tabWidget.setCurrentWidget(self.scriptingTab)

    def onLogTriggered(self):
        self.tabWidget.setCurrentWidget(self.logTab)

    def onActionTriggered(self, toggled: bool):
        action = self.sender()
        windowclass = self._action2windowclass[action.objectName()]
        logger.debug(f'Window class: {windowclass}')
        assert issubclass(windowclass, QtWidgets.QWidget)
        try:
            win = self._windows[windowclass.__name__]
            win.show()
            if win.isMinimized():
                win.showNormal()
            win.raise_()
            win.setFocus()
        except KeyError:
            assert issubclass(windowclass, WindowRequiresDevices)
            assert issubclass(windowclass, QtWidgets.QWidget)
            self.addSubWindow(windowclass, singleton=True)

    def addSubWindow(self, windowclass, singleton: bool = True) -> Optional[WindowRequiresDevices]:
        if windowclass.checkRequirements():
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

    def onDeviceAdded(self, device: str):
        if not [ds for ds in self._devicestatuswidgets if ds.devicename == device]:
            # device status widget not yet exists
            ds = DeviceStatus(devicename=device)
            self._devicestatuswidgets.append(ds)
            self.deviceStatusBarLayout.insertWidget(self.deviceStatusBarLayout.count() - 1, ds, stretch=0)
            logger.debug(f'Added device status widget for device {device}')
        else:
            logger.debug(f'Device status widget already exists for device {device}')

    def onDeviceRemoved(self, device: str):
        try:
            statuswidget = [ds for ds in self._devicestatuswidgets if ds.devicename == device][0]
        except IndexError:
            logger.warning(f'Cannot remove device status widget for device {device}: does not exist.')
            return
        self._devicestatuswidgets.remove(statuswidget)
        statuswidget.destroy(True, True)
        statuswidget.deleteLater()
        logger.debug(f'Device status widget for device {device} has been removed.')

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

    def showPattern(self, exposure: Exposure, keepzoom: Optional[bool] = None, title: Optional[str] = None):
        if title is None:
            title = f'{exposure.header.prefix}/{exposure.header.fsn}: {exposure.header.title} @ {exposure.header.distance[0]:.2f} mm'
        self.plotimage.setExposure(exposure, keepzoom, title)
        self.tabWidget.setCurrentWidget(self.patternTab)

    def showCurve(self, curve: Union[Curve, Exposure]):
        if isinstance(curve, Exposure):
            title = f'{curve.header.prefix}/{curve.header.fsn}: {curve.header.title} @ {curve.header.distance[0]:.2f} mm'
            curve = curve.radial_average()
        else:
            title = None
        self.plotcurve.clear()
        self.plotcurve.addCurve(curve, label=title)
        self.plotcurve.replot()
        self.tabWidget.setCurrentWidget(self.curveTab)
