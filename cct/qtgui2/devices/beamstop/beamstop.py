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
        self.inToolButton.clicked.connect(self.moveBeamstopIn)
        self.outToolButton.clicked.connect(self.moveBeamstopOut)
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

    def moveBeamstopIn(self):
        try:
            self.instrument.beamstop.moveIn()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.window(), 'Cannot move beam-stop', exc.args[0])

    def moveBeamstopOut(self):
        try:
            self.instrument.beamstop.moveOut()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self.window(), 'Cannot move beam-stop', exc.args[0])