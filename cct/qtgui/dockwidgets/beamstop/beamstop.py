import logging
from typing import Union

from PyQt5 import QtWidgets, QtGui

from .beamstop_ui import Ui_DockWidget
from ...core.mixins import ToolWindow
from ....core.devices import Device
from ....core.devices.motor import Motor
from ....core.instrument.instrument import Instrument
from ....core.instrument.privileges import PRIV_BEAMSTOP

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class BeamStopDockWidget(QtWidgets.QDockWidget, Ui_DockWidget, ToolWindow):
    required_privilege = PRIV_BEAMSTOP
    required_devices = ['Motor_BeamStop_X', 'Motor_BeamStop_Y']

    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QDockWidget.__init__(self, *args, **kwargs)
        self._moving = False
        self._movetargets=[]
        self.setupToolWindow(credo)
        self.setupUi(self)

    def setupUi(self, DockWidget):
        Ui_DockWidget.setupUi(self,DockWidget)
        self.beamstopInToolButton.clicked.connect(self.onBeamstopIn)
        self.beamstopOutToolButton.clicked.connect(self.onBeamstopOut)
        self.checkBeamStop()

    def onBeamstopIn(self):
        logger.debug('onBeamstopIn')
        self._movetargets=[('BeamStop_X', self.credo.config['beamstop']['in'][0]),
                           ('BeamStop_Y', self.credo.config['beamstop']['in'][1])]
        self.nextBeamstopMove()

    def onBeamstopOut(self):
        logger.debug('onBeamstopOut')
        self._movetargets=[('BeamStop_X', self.credo.config['beamstop']['out'][0]),
                           ('BeamStop_Y', self.credo.config['beamstop']['out'][1])]
        self.nextBeamstopMove()

    def nextBeamstopMove(self):
        try:
            motor, target = self._movetargets.pop()
        except IndexError:
            self.checkBeamStop()
            return
        else:
            self._moving=True
            self.credo.motors[motor].moveto(target)
        return

    def onMotorStop(self, motor: Motor, targetpositionreached: bool):
        self.nextBeamstopMove()
        self._moving = False
        self.checkBeamStop()

    def onMotorStart(self, motor: Motor):
        self._moving = True
        self.checkBeamStop()

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        if motor.name == 'BeamStop_X':
            self.checkBeamStop(newposition, None)
        elif motor.name == 'BeamStop_Y':
            self.checkBeamStop(None, newposition)
        else:
            raise ValueError('Invalid motor name: {}'.format(motor.name))
        return False

    def checkBeamStop(self, x=None, y=None):
        logger.debug('checkBeamStop({}, {})'.format(x,y))
        assert isinstance(self.credo, Instrument)
        try:
            bsstate=self.credo.get_beamstop_state(bsx=x, bsy=y)
        except KeyError:
            bsstate = 'unknown'
        self.beamstopInToolButton.setEnabled((bsstate!='in') and (not self._moving) and (not self._movetargets))
        self.beamstopOutToolButton.setEnabled((bsstate!='out') and (not self._moving) and (not self._movetargets))
        logger.debug('')
        if bsstate=='in':
            iconfile='beamstop-in.svg'
        elif bsstate=='out':
            iconfile='beamstop-out.svg'
        else:
            iconfile='beamstop-inconsistent.svg'
        logger.debug('Beamstop state: {}'.format(bsstate))
        self.beamstopIconLabel.setPixmap(QtGui.QPixmap(":/icons/{}".format(iconfile)).scaled(48,48))
        self.beamstopIconLabel.setToolTip('Beamstop is currently {}'.format(bsstate))

    def onDeviceReady(self, device: Union[Device, Motor]):
        logger.debug('OnDeviceReady')
        super().onDeviceReady(device)
        self.checkBeamStop()
        logger.debug('OnDeviceReady done')
