import logging
import weakref

import pkg_resources

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from PyQt5 import QtWidgets, QtCore, QtGui

from ...core.instrument.instrument import Instrument
from ...core.services.interpreter import Interpreter
from ...core.services.accounting import Accounting
from ...core.devices import Device
from .mainwindow_ui import Ui_MainWindow
from .devicestatusbar import DeviceStatusBar
from ..setup.sampleeditor import SampleEditor
from ..tools.capillarymeasurement import CapillaryMeasurement
from ..tools.maskeditor import MaskEditor
from ..tools.optimizegeometry import OptimizeGeometry
from ..tools.datareduction import DataReduction
from ..setup.geometry import GeometrySetup
from ..measurement.scripteditor import ScriptEditor
from ..measurement.scan import ScanMeasurement
from ..measurement.transmission import TransmissionMeasurement
from ..measurement.singleexposure import SingleExposure
from ..setup.calibration import Calibration
from ..setup.project import ProjectSetup
from ..setup.users import UserManager
from ..setup.configeditor import ConfigEditor
from ..view.scanview import ScanViewer
from ..view.exposureview import ExposureView
from ..devices.xray_source import XraySource
from ..devices.detector import Detector
from ..devices.motor import MotorOverview
from ..devices.circulator import TemperatureController
from ..devices.vacuum import VacuumGauge
from ..diagnostics.resourceusage import ResourceUsage
from .logviewer import LogViewer
from .collectinghandler import CollectingHandler
from .. import dockwidgets

class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, *args, **kwargs):
        self.credo=kwargs.pop('credo')
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        self.windowdict={}
        self.setupUi(self)
        self._credo_connections=[]
        self._accounting_connections=[]
        self._interpreter_connections=[]

    def setupUi(self, MainWindow):
        Ui_MainWindow.setupUi(self,MainWindow)
        self._dockwidgetinfo={
            self.actionAccounting:dockwidgets.Accounting,
            self.actionFSN_counters:dockwidgets.FSNCounter,
            self.actionShutter_and_beamstop:dockwidgets.ShutterAndBeamstop,
            self.actionResource_usage:dockwidgets.ResourceConsumption,
        }
        self._action_to_windowclass = {
            self.actionSample_editor:SampleEditor,
            self.actionCapillary_sizing:CapillaryMeasurement,
            self.actionMask_editor:MaskEditor,
            self.actionOptimize_geometry:OptimizeGeometry,
            self.actionGeometry_editor:GeometrySetup,
            self.actionCalibration:Calibration,
            self.actionScript:ScriptEditor,
            self.actionProject_management:ProjectSetup,
            self.actionView_scans:ScanViewer,
            self.actionView_images_and_curves:ExposureView,
            self.actionX_ray_source:XraySource,
            self.actionDetector:Detector,
            self.actionMotors:MotorOverview,
            self.actionVacuum_gauge:VacuumGauge,
            self.actionTemperature_stage:TemperatureController,
            self.actionScan:ScanMeasurement,
            self.actionTransmission:TransmissionMeasurement,
            self.actionResource_consumption:ResourceUsage,
            self.actionSingle_exposure:SingleExposure,
            self.actionData_reduction:DataReduction,
            self.actionUser_management:UserManager,
            self.actionEdit_configuration:ConfigEditor,
        }
        self._dockwidgets = {}


        self.actionQuit.triggered.connect(self.onQuit)
        self.actionSave_settings.triggered.connect(self.onSaveSettings)
        self.actionAbout.triggered.connect(self.onAbout)
        self.actionAbout_Qt.triggered.connect(self.onAboutQt)
        for action in self._action_to_windowclass:
            assert isinstance(action, QtWidgets.QAction)
            action.triggered.connect(self.openWindow)
        layout=QtWidgets.QVBoxLayout()
        self.logViewerGroupBox.setLayout(layout)
        self.logViewer = LogViewer(self.logViewerGroupBox)
        layout.addWidget(self.logViewer)
        logging.root.addHandler(self.logViewer)
        for record in CollectingHandler.instance.collected:
            self.logViewer.emit(record)
        logging.root.removeHandler(CollectingHandler.instance)
        for action in [self.actionAccounting, self.actionFSN_counters, self.actionShutter_and_beamstop, self.actionResource_usage]:
            action.setChecked(False)
            action.toggled.connect(self.showHideDockWidget)
            action.toggle()
        assert isinstance(self.credo, Instrument)
        self._credo_connections=[
            self.credo.connect('shutdown', self.onCredoShutdown),
            self.credo.connect('devices-ready', self.onCredoDevicesReady),
            self.credo.connect('device-connected', self.onCredoDeviceConnected),
            self.credo.connect('device-disconnected', self.onCredoDeviceDisconnected)
        ]
        ip = self.credo.services['interpreter']
        assert isinstance(ip, Interpreter)
        self._interpreter_connections=[
            ip.connect('cmd-return', self.onCmdReturn),
            ip.connect('cmd-fail', self.onCmdFail),
            ip.connect('pulse', self.onCmdPulse),
            ip.connect('progress', self.onCmdProgress),
            ip.connect('cmd-message', self.onCmdMessage),
            ip.connect('idle-changed', self.onInterpreterIdleChanged)
        ]
        acc = self.credo.services['accounting']
        assert isinstance(acc, Accounting)
        self._accounting_connections=[acc.connect('privlevel-changed', lambda *args:self.updateActionEnabledStates()) ]
        self.setAttribute(QtCore.Qt.WA_QuitOnClose, True)
        self.progressBar.hide()
        if self.credo.online:
            self.credo.connect_devices()
        self.updateActionEnabledStates()
        self.executePushButton.clicked.connect(self.onExecuteCommandLine)
        self.commandLineEdit.returnPressed.connect(self.onExecuteCommandLine)
        self.deviceStatusBar=DeviceStatusBar(self, self.credo)
        self.deviceStatusBarLayout.addWidget(self.deviceStatusBar)

    def onExecuteCommandLine(self):
        interpreter = self.credo.services['interpreter']
        assert isinstance(interpreter, Interpreter)
        if self.executePushButton.text()=='Execute':
            interpreter.execute_command(self.commandLineEdit.text())
        else:
            assert self.executePushButton.text() == 'Stop'
            interpreter.kill()

    def onInterpreterIdleChanged(self, interpreter:Interpreter, idle:bool):
        self.commandLineEdit.setEnabled(idle)
        if idle:
            self.executePushButton.setText('Execute')
            self.executePushButton.setIcon(QtGui.QIcon.fromTheme('system-run'))
        else:
            self.executePushButton.setText('Stop')
            self.executePushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))

    def onCmdReturn(self, interpreter:Interpreter, commandname:str, retval):
        self.progressBar.setVisible(False)

    def onCmdFail(self, interpreter:Interpreter, commandname:str, exception, traceback:str):
        logger.error('Error in command {}: {}\n{}'.format(commandname, str(exception), traceback))

    def onCmdPulse(self, interpreter:Interpreter, commandname:str, description:str):
        self.progressBar.setVisible(True)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)
        self.progressBar.setValue(0)
        self.progressBar.setFormat(description)

    def onCmdProgress(self, interpreter:Interpreter, commandname:str, description:str, fraction:float):
        self.progressBar.setVisible(True)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100000)
        self.progressBar.setValue(100000*fraction)
        self.progressBar.setFormat(description)

    def onCmdMessage(self, interpreter:Interpreter, commandname:str, message:str):
        logger.info(message)

    def closeEvent(self, event:QtGui.QCloseEvent):
        if self.credo.is_running():
            event.ignore()
            return self.onQuit()
        else:
            event.accept()

    def onCredoShutdown(self, credo:Instrument):
        logger.debug('Shutdown signal received.')
        self.cleanup()
        self.close()

    def updateActionEnabledStates(self):
        for action in self._action_to_windowclass:
            reqOk=self._action_to_windowclass[action].testRequirements(self.credo)
            action.setEnabled(reqOk)
            if action in list(self.windowdict.keys()):
                try:
                    self.windowdict[action].setEnabled(reqOk)
                except RuntimeError:
                    del self.windowdict[action]
        for action in list(self._dockwidgetinfo.keys()):
            reqOk=self._dockwidgetinfo[action].testRequirements(self.credo)
            action.setEnabled(reqOk)
            if not reqOk and action.isChecked():
                action.setChecked(False)

    def onCredoDevicesReady(self, credo:Instrument):
        self.updateActionEnabledStates()

    def onCredoDeviceConnected(self, credo:Instrument, device:Device):
        pass

    def onCredoDeviceDisconnected(self, credo:Instrument, device:Device, expected:bool):
        self.updateActionEnabledStates()

    def showHideDockWidget(self, state:bool):
        action= self.sender()
        assert isinstance(action, QtWidgets.QAction)
        if not state:
            # we need to close the dockwidget
            try:
                self._dockwidgets[action].destroyed.disconnect(action.setChecked)
                self._dockwidgets[action].close()
                del self._dockwidgets[action]
            except RuntimeError:
                del self._dockwidgets[action]
            except KeyError:
                pass
        else:
            assert action not in self._dockwidgets
            cls = [self._dockwidgetinfo[a] for a in self._dockwidgetinfo if a is action][0]
            self._dockwidgets[action]= cls(self, credo=self.credo)
            self._dockwidgets[action].setSizePolicy(
                QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum,
                                      QtWidgets.QSizePolicy.Minimum))
            self._dockwidgets[action].setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self._dockwidgets[action].destroyed.connect(lambda x=False: action.setChecked(False))
            self.addDockWidget(QtCore.Qt.TopDockWidgetArea, self._dockwidgets[action])

    def onQuit(self):
        assert isinstance(self.credo, Instrument)
        self.credo.save_state()
        if self.credo.shutdown_requested:
            # a shutdown is already pending, maybe the user is impatient
            if not QtWidgets.QMessageBox.question(self, 'Really shutdown?', 'Shutdown operation is pending. Do you really want to force quit? Devices might not be disconnected cleanly.'):
                return
            else:
                self.onCredoShutdown(self.credo)
        else:
            self.credo.shutdown()

    def onSaveSettings(self):
        assert isinstance(self.credo, Instrument)
        self.credo.save_state()
        logger.info('State saved.')

    def onAbout(self):
        QtWidgets.QMessageBox.about(self, 'About cct',
'''Credo Control Tool v{}

Copyright (c) 2017, András Wacha

All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.'''.format(pkg_resources.get_distribution('cct').version))

    def onAboutQt(self):
        QtWidgets.QMessageBox.aboutQt(self, 'About Qt')

    def openWindow(self):
        action = self.sender()
        assert isinstance(action, QtWidgets.QAction)
        windowclass = self._action_to_windowclass[action]
        try:
            logger.debug('Trying to find window for action {}'.format(action.objectName()))
            self.windowdict[action].show()
            self.windowdict[action].raise_()
        except (KeyError, RuntimeError):
            logger.debug('Window not found for action {}; creating new one, an instance of {}'.format(action.objectName(), str(windowclass)))
            self.windowdict[action]=windowclass(parent=None, credo=weakref.proxy(self.credo))
            #self.windowdict[action].setWindowIcon()
            return self.openWindow()
        return True

    def cleanup(self):
        for c in self._interpreter_connections:
            self.credo.services['interpreter'].disconnect(c)
        self._interpreter_connections = []
        for c in self._credo_connections:
            self.credo.disconnect(c)
        self._credo_connections=[]
        for action in list(self._dockwidgets.keys()):
            try:
                self._dockwidgets[action].close()
                self._dockwidgets[action].destroy()
            except RuntimeError:
                pass
            del self._dockwidgets[action]
        for action in list(self.windowdict.keys()):
            try:
                self.windowdict[action].close()
                self.windowdict[action].destroy()
            except RuntimeError:
                pass
            del self.windowdict[action]
        logging.root.removeHandler(self.logViewer)
