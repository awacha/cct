from PyQt5 import QtWidgets, QtGui
from .beamstop_ui import Ui_Frame
from ...utils.window import WindowRequiresDevices


class BeamstopIndicator(QtWidgets.QFrame, WindowRequiresDevices, Ui_Frame):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Frame):
        super().setupUi(Frame)
        self.instrument.beamstop.stateChanged.connect(self.onBeamstopStateChanged)
        self.inToolButton.clicked.connect(self.instrument.beamstop.moveIn)
        self.outToolButton.clicked.connect(self.instrument.beamstop.moveOut)
        self.onBeamstopStateChanged()

    def onBeamstopStateChanged(self):
        if self.instrument.beamstop.state == self.instrument.beamstop.States.In:
            self.statusLabel.setPixmap(QtGui.QPixmap(':/icons/beamstop-in.svg'))
            self.inToolButton.setEnabled(False)
            self.outToolButton.setEnabled(True)
        elif self.instrument.beamstop.state == self.instrument.beamstop.States.Out:
            self.statusLabel.setPixmap(QtGui.QPixmap(':/icons/beamstop-out.svg'))
            self.inToolButton.setEnabled(True)
            self.outToolButton.setEnabled(False)
        elif self.instrument.beamstop.state == self.instrument.beamstop.States.Moving:
            self.statusLabel.setPixmap(QtGui.QPixmap(':/icons/beamstop-moving.svg'))
            self.inToolButton.setEnabled(False)
            self.outToolButton.setEnabled(False)
        elif self.instrument.beamstop.state == self.instrument.beamstop.States.Undefined:
            self.statusLabel.setPixmap(QtGui.QPixmap(':/icons/beamstop-inconsistent.svg'))
            self.inToolButton.setEnabled(True)
            self.outToolButton.setEnabled(True)
