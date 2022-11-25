import logging
from typing import List

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Slot

from .devicevariablelogging.devicevariablelogger import DeviceVariableLoggerUI
from .devicevariablemeasurement_ui import Ui_Form
from ..utils.window import WindowRequiresDevices
from ...core2.instrument.components.devicestatus import DeviceStatusLogger

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DeviceVariableMeasurement(WindowRequiresDevices, QtWidgets.QWidget, Ui_Form):
    loggerwidgets = List[DeviceVariableLoggerUI]

    def __init__(self, **kwargs):
        self.loggerwidgets = []
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.instrument.devicestatus)
        self.addLoggerToolButton.clicked.connect(self.onAddClicked)
        self.startAllToolButton.clicked.connect(self.startAll)
        self.stopAllToolButton.clicked.connect(self.stopAll)
        self.scrollAreaWidgetContents.setLayout(QtWidgets.QVBoxLayout())
        self.instrument.devicelogmanager.rowsInserted.connect(self.onRowsInserted)
        self.instrument.devicelogmanager.rowsRemoved.connect(self.onRowsRemoved)
        self.instrument.devicelogmanager.modelReset.connect(self.onModelReset)
        self.onModelReset()

    @Slot(QtCore.QModelIndex, int, int)
    def onRowsInserted(self, parent: QtCore.QModelIndex, first:int, last:int):
        layout: QtWidgets.QVBoxLayout = self.scrollArea.widget().layout()
        for i in range(first, last+1):
            widget = DeviceVariableLoggerUI(instrument=self.instrument, devicelogger=self.instrument.devicelogmanager[i])
            layout.insertWidget(i, widget)

    @Slot(QtCore.QModelIndex, int, int)
    def onRowsRemoved(self, parent: QtCore.QModelIndex, first: int, last: int):
        pass  # the widget should be destroyed when the DeviceStatusLogger instance is destroyed

    @Slot()
    def onModelReset(self):
        self.checkForDestroyedWidgets()
        for widget in self.loggerwidgets:
            try:
                widget.deleteLater()
            except RuntimeError:
                pass
        for widget in self.scrollArea.widget().layout().children():
            self.scrollArea.widget().layout().removeWidget(widget)
        self.loggerwidgets = []
        logger.debug(f'Calling onRowsInserted, rowcount is {self.instrument.devicelogmanager.rowCount(QtCore.QModelIndex())}')
        self.onRowsInserted(QtCore.QModelIndex(), 0, self.instrument.devicelogmanager.rowCount(QtCore.QModelIndex())-1)

    @Slot()
    def startAll(self):
        self.instrument.devicelogmanager.startAll()

    @Slot()
    def stopAll(self):
        self.instrument.devicelogmanager.stopAll()

    @Slot()
    def onAddClicked(self):
        self.instrument.devicelogmanager.insertRow(len(self.instrument.devicelogmanager), QtCore.QModelIndex())
        lgr = self.instrument.devicelogmanager[len(self.instrument.devicelogmanager)-1]
        for rowindex in self.treeView.selectionModel().selectedRows(0):
            if not rowindex.parent().isValid():
                continue
            logger.debug(
                f'Adding logger for variable {rowindex.parent().data(QtCore.Qt.ItemDataRole.EditRole)}/{rowindex.data((QtCore.Qt.ItemDataRole.EditRole))}')
            try:
                lgr.addRecordedVariable(rowindex.parent().data(QtCore.Qt.ItemDataRole.EditRole), rowindex.data(QtCore.Qt.ItemDataRole.EditRole))
            except ValueError as ve:
                QtWidgets.QMessageBox.critical(
                    self, f'Cannot add variable',
                    f'Error while adding variable '
                    f'{rowindex.parent().data(QtCore.Qt.ItemDataRole.EditRole)}/{rowindex.data(QtCore.Qt.ItemDataRole.EditRole)}: {ve}')

    @Slot()
    def onLoggerDestroyed(self):
        self.checkForDestroyedWidgets()

    def checkForDestroyedWidgets(self):
        newloggers = []
        for lw in self.loggerwidgets:
            try:
                lw.objectName()
            except RuntimeError:
                # wrapped C/C++ object has been deleted
                pass
            else:
                newloggers.append(lw)
        self.loggerwidgets = newloggers