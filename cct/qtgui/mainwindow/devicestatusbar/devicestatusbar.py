from PyQt5 import QtWidgets, QtGui

from .devicestatus import DeviceStatus
from ....core.instrument.instrument import Instrument


class DeviceStatusBar(QtWidgets.QWidget):
    def __init__(self, parent, credo: Instrument):
        super().__init__(parent)
        self.credo = credo
        self._statusindicators = []
        self.setupUi(self)

    def setupUi(self, Form):
        self.layout = QtWidgets.QHBoxLayout(self)
        self.setLayout(self.layout)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        for d in sorted(self.credo.devices):
            dev = self.credo.devices[d]
            self._statusindicators.append(DeviceStatus(self, dev))
            self.layout.addWidget(self._statusindicators[-1])
        self.layout.addStretch(1)

    def closeEvent(self, event: QtGui.QCloseEvent):
        for i in self._statusindicators:
            i.close()
            del i
        for dev in self._connections:
            for c in self._connections[dev]:
                try:
                    dev.disconnect(c)
                except:
                    pass
        self._connections = {}
        event.accept()
