import logging
from typing import List

from PyQt5 import QtCore, QtWidgets

from .devicevariablelogging.devicevariablelogger import DeviceVariableLoggerUI
from .devicevariablemeasurement_ui import Ui_Form
from ..utils.window import WindowRequiresDevices
from ...core2.instrument.components.devicestatus import DeviceStatusLogger

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class DeviceVariableMeasurement(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    loggers = List[DeviceStatusLogger]

    def __init__(self, **kwargs):
        self.loggers = []
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.devicestatus)
        self.addLoggerToolButton.clicked.connect(self.onAddClicked)
        self.startAllToolButton.clicked.connect(self.startAll)
        self.stopAllToolButton.clicked.connect(self.stopAll)
        self.scrollAreaWidgetContents.setLayout(QtWidgets.QVBoxLayout())

    def startAll(self):
        for l in self.loggers:
            try:
                l.startRecording()
            except RuntimeError:
                pass

    def stopAll(self):
        for l in self.loggers:
            try:
                l.stopRecording()
            except RuntimeError:
                pass

    def onAddClicked(self):
        l = DeviceStatusLogger(self.instrument.devicemanager)
        for rowindex in self.treeView.selectionModel().selectedRows(0):
            if not rowindex.parent().isValid():
                continue
            logger.debug(f'')
            logger.debug(
                f'Adding logger for variable {rowindex.parent().data(QtCore.Qt.EditRole)}/{rowindex.data((QtCore.Qt.EditRole))}')
            try:
                l.addRecordedVariable(rowindex.parent().data(QtCore.Qt.EditRole), rowindex.data(QtCore.Qt.EditRole))
            except ValueError as ve:
                QtWidgets.QMessageBox.critical(
                    self, f'Cannot add variable',
                    f'Error while adding variable '
                    f'{rowindex.parent().data(QtCore.Qt.EditRole)}/{rowindex.data(QtCore.Qt.EditRole)}: {ve}')
        l.destroyed.connect(self.onLoggerDestroyed)
        widget = DeviceVariableLoggerUI(instrument=self.instrument, devicelogger=l)
        self.loggers.append(l)
        self.scrollArea.widget().layout().addWidget(widget)

    def onLoggerDestroyed(self):
        newloggers = []
        for l in self.loggers:
            try:
                l.objectName()
            except RuntimeError:
                # wrapped C/C++ object has been deleted
                pass
            else:
                newloggers.append(l)
        self.loggers = newloggers
