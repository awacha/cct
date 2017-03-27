import logging
import weakref

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
from ....core.instrument.instrument import Instrument
from ....core.services.interpreter import Interpreter
from ....core.commands import Command
from ....core.instrument.privileges import PRIV_LAYMAN
from ....core.devices import Device, Motor
from typing import Union, List
from PyQt5 import QtCore, QtGui, QtWidgets


class ToolWindow(object):
    required_devices = []
    required_privilege = PRIV_LAYMAN

    def __init__(self, credo, required_devices=[]):
        self._busy = False
        assert isinstance(self, QtWidgets.QWidget)
        try:
            self.credo = weakref.proxy(credo)
        except TypeError:
            self.credo = credo
        assert isinstance(self.credo, Instrument)  # this works even if self.credo is a weakproxy to Instrument
        self._device_connections = {}
        for d in self.required_devices + required_devices:
            self.requireDevice(d)
        self._privlevelconnection = self.credo.services['accounting'].connect('privlevel-changed', self.onPrivLevelChanged)
        self._credoconnections = [self.credo.connect('config-changed', self.updateUiFromConfig)]
        self._interpreterconnections = []
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

    @classmethod
    def testRequirements(cls, credo:Instrument):
        """Return True if the instrument is in a state when this window can be opened. If this
        class method returns False, the window won't be opened or will be closed or disabled if
        it is already open."""
        if not credo.services['accounting'].has_privilege(cls.required_privilege):
            return False
        for r in cls.required_devices:
            try:
                if not credo.get_device(r).ready:
                    return False
            except KeyError:
                return False
        return True

    def requireDevice(self, devicename: str):
        assert isinstance(self.credo, Instrument)
        try:
            device = self.credo.get_device(devicename)
        except KeyError:
            # ToDo
            raise
        assert isinstance(device, (Device, Motor))
        if device in self._device_connections:
            # do not require the same device twice.
            return
        self._device_connections[device] = [
            device.connect('variable-change', self.onDeviceVariableChange),
            device.connect('error', self.onDeviceError),
            device.connect('disconnect', self.onDeviceDisconnect),
            device.connect('ready', self.onDeviceReady)
        ]
        if isinstance(device, Motor):
            self._device_connections[device].extend([
                device.connect('position-change', self.onMotorPositionChange),
                device.connect('stop', self.onMotorStop),
                device.connect('start', self.onMotorStart),
            ])

    def onPrivLevelChanged(self, accountingservice, privlevel):
        assert isinstance(self, QtWidgets.QWidget)
        if privlevel < self.required_privilege:
            self.cleanup()
            self.close()

    def onDeviceVariableChange(self, device: Union[Device, Motor], variablename: str, newvalue):
        return False

    def onDeviceError(self, device: Union[Device, Motor], variablename: str, exception: Exception,
                      formatted_traceback: str):
        return False

    def onDeviceDisconnect(self, device: Union[Device, Motor], abnormal_disconnection: bool):
        if self._busy:
            self.setEnabled(False)
        else:
            self.close()
            self.cleanup()
        return False

    def onDeviceReady(self, device: Union[Device, Motor]):
        self.setEnabled(True)
        return False

    def onMotorPositionChange(self, motor: Motor, newposition: float):
        return False

    def onMotorStop(self, motor: Motor, targetpositionreached: bool):
        return False

    def onMotorStart(self, motor:Motor):
        return False

    def unrequireDevice(self, device:Union[str, Device, Motor]):
        if isinstance(device, str):
            device = self.credo.get_device(device)
        try:
            for cid in self._device_connections[device]:
                device.disconnect(cid)
        except KeyError:
            pass
        finally:
            del self._device_connections[device]

    def cleanup(self):
        logger.debug('Cleanup() called on ToolWindow {}'.format(self.objectName()))
        self.cleanupAfterCommand()
        for d in list(self._device_connections.keys()):
            self.unrequireDevice(d)
        if self._privlevelconnection is not None:
            self.credo.services['accounting'].disconnect(self._privlevelconnection)
            self._privlevelconnection=None
        for c in self._credoconnections:
            self.credo.disconnect(c)
        self._credoconnections = []
        logger.debug('Cleanup() finished on ToolWindow {}'.format(self.objectName()))

    def event(self, event:QtCore.QEvent):
        if event.type()==QtCore.QEvent.ActivationChange:
            self.activationChangeEvent(event)
        return QtWidgets.QWidget.event(self, event)

    def activationChangeEvent(self, event:QtCore.QEvent):
        assert isinstance(self, QtWidgets.QWidget)
        if self.windowState() & QtCore.Qt.WindowActive:
            logger.debug('ToolWindow {} activation changed: it is now active. State: {}, {}'.format(self.objectName(), self.isActiveWindow(), self.windowState()&0xffff))
        else:
            logger.debug('ToolWindow {} activation changed: it is now not active. State: {}, {}'.format(self.objectName(), self.isActiveWindow(), self.windowState()&0xffff))

    def closeEvent(self, event:QtGui.QCloseEvent):
        assert isinstance(self, QtWidgets.QWidget)
        logger.debug('CloseEvent received for ToolWindow {}'.format(self.objectName()))
        if self._busy:
            result = QtWidgets.QMessageBox.question(
                    self, "Really close?",
                    "The process behind this window is still working. If you close this window now, "
                    "you can break something. Are you <b>really</b> sure?")
            logger.debug('Question result: {}'.format(result))
            if result != QtWidgets.QMessageBox.Yes:
                event.ignore()
                logger.debug('Phew!')
                return
            else:
                logger.debug("Closing window {} forced.".format(self.objectName()))
        self.cleanup()
        if isinstance(self, QtWidgets.QDockWidget):
            return QtWidgets.QDockWidget.closeEvent(self, event)
        elif isinstance(self, QtWidgets.QMainWindow):
            return QtWidgets.QMainWindow.closeEvent(self, event)
        else: #isinstance(self, QtWidgets.QWidget)
            return QtWidgets.QWidget.closeEvent(self, event)

    def setBusy(self):
        assert isinstance(self, QtWidgets.QWidget)
        self._busy = True

    def setIdle(self):
        self._busy = False

    def updateUiFromConfig(self, credo):
        """This is called whenever the configuration changed"""
        pass

    def isBusy(self):
        return self._busy

    def cleanupAfterCommand(self):
        for c in self._interpreterconnections:
            self.credo.services['interpreter'].disconnect(c)
        self._interpreterconnections = []
        try:
            self.progressBar.setVisible(False)
        except (AttributeError, RuntimeError):
            pass

    def onCmdReturn(self, interpreter:Interpreter, cmdname:str, retval):
        self.cleanupAfterCommand()

    def onCmdFail(self, interpreter:Interpreter, cmdname:str, exception:Exception, traceback:str):
        pass

    def onCmdProgress(self, interpreter:Interpreter, cmdname:str, description:str, fraction:float):
        try:
            self.progressBar.setVisible(True)
            self.progressBar.setMinimum(0)
            self.progressBar.setMaximum(100000)
            self.progressBar.setValue(100000*fraction)
            self.progressBar.setFormat(description)
        except (AttributeError, RuntimeError):
            pass

    def onCmdPulse(self, interpreter:Interpreter, cmdname:str, description:str):
        try:
            self.progressBar.setVisible(True)
            self.progressBar.setMinimum(0)
            self.progressBar.setMaximum(0)
            self.progressBar.setValue(0)
            self.progressBar.setFormat(description)
        except (AttributeError, RuntimeError):
            pass

    def onCmdMessage(self, interpreter:Interpreter, cmdname:str, message:str):
        pass

    def onCmdDetail(self, interpreter:Interpreter, cmdname:str, detail):
        pass

    def executeCommand(self, command:Command, arguments:List[str]):
        interpreter = self.credo.services['interpreter']
        if self._interpreterconnections:
            raise ValueError('Cannot run another command: either the previous command is still running or it has not been cleaned up yet.')
        self._interpreterconnections = [interpreter.connect('cmd-return', self.onCmdReturn),
                                        interpreter.connect('cmd-fail', self.onCmdFail),
                                        interpreter.connect('cmd-detail', self.onCmdDetail),
                                        interpreter.connect('progress', self.onCmdProgress),
                                        interpreter.connect('pulse', self.onCmdPulse),
                                        interpreter.connect('cmd-message', self.onCmdMessage),]
        assert isinstance(interpreter, Interpreter)
        try:
            interpreter.execute_command(command, arguments)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, 'Error executing command', 'Cannot execute command {}: {}'.format(command.name, exc.args[0]))
            self.cleanupAfterCommand()
