from typing import Any
import logging

from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import pyqtSlot as Slot

from .shutter_ui import Ui_Frame
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.instrument import Instrument
from ....core2.devices import DeviceType
from ....core2.devices.xraysource.genix.frontend import GeniX

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ShutterIndicator(QtWidgets.QFrame, WindowRequiresDevices, Ui_Frame):
    required_devicetypes = [DeviceType.Source]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Frame):
        super().setupUi(Frame)
        self.toolButton.toggled.connect(self.onToolButtonToggled)
        self.setToolButtonState()

    @Slot()
    def onConnectionLost(self):
        self.setToolButtonState()

    @Slot(bool)
    def onConnectionEnded(self, expected: bool):
        self.setToolButtonState()

    @Slot(str, object, object)
    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        if isinstance(self.sender(), GeniX):
            if name in ['interlock', 'shutter']:
                self.setToolButtonState()

    def setToolButtonState(self):
        try:
            genix = self.instrument.devicemanager.source()
        except (IndexError, KeyError):
            logger.debug('No GeniX instrument')
            self.toolButton.setEnabled(False)
            self.toolButton.setChecked(False)
            return
        if not genix.isOnline():
            self.toolButton.setEnabled(False)
            self.toolButton.setChecked(False)
            return
        try:
            self.toolButton.setEnabled(genix['interlock'])
        except (KeyError, GeniX.DeviceError):
            logger.debug('No interlock')
            self.toolButton.setEnabled(False)
        try:
            self.toolButton.setIcon(
                QtGui.QIcon(
                    QtGui.QPixmap(
                        ':/icons/beamshutter_open.svg' if genix['shutter'] else ':/icons/beamshutter_closed.svg')))
            self.toolButton.blockSignals(True)
            self.toolButton.setChecked(genix['shutter'])
            self.toolButton.blockSignals(False)
        except (KeyError, GeniX.DeviceError):
            logger.debug('No shutter')
            self.toolButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/beamshutter_closed.svg')))
            self.toolButton.blockSignals(True)
            self.toolButton.setChecked(False)
            self.toolButton.blockSignals(False)

    @Slot()
    def onToolButtonToggled(self):
        try:
            genix = self.instrument.devicemanager.source()
            assert isinstance(genix, GeniX)
        except (IndexError, KeyError):
            self.setToolButtonState()
            return
        genix.moveShutter(self.toolButton.isChecked())