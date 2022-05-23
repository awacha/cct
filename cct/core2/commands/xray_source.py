import logging

from PyQt5.QtCore import pyqtSlot as Slot

from .command import Command
from .commandargument import StringChoicesArgument
from ..devices.xraysource import GeniX

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class XraySourceCommand(Command):
    def _connectXraySource(self):

        self.xraysource().commandResult.connect(self.onXraySourceCommandResult)
        self.xraysource().shutter.connect(self.onShutter)
        self.xraysource().powerStateChanged.connect(self.onXraySourcePowerStateChanged)

    def _disconnectXraySource(self):
        self.xraysource().commandResult.disconnect(self.onXraySourceCommandResult)
        self.xraysource().shutter.disconnect(self.onShutter)
        self.xraysource().powerStateChanged.disconnect(self.onXraySourcePowerStateChanged)

    @Slot(bool)
    def onShutter(self, state: bool):
        pass

    @Slot(bool, str, str)
    def onXraySourceCommandResult(self, success: bool, command: str, message: str):
        pass

    @Slot(str)
    def onXraySourcePowerStateChanged(self, state: str):
        pass

    def xraysource(self) -> GeniX:
        try:
            dev = self.instrument.devicemanager.source()
        except (KeyError, IndexError):
            raise self.CommandException('X-ray source not connected.')
        return dev


class Shutter(XraySourceCommand):
    name = 'shutter'
    description = "Open or close the shutter."
    arguments = [StringChoicesArgument('state', 'required shutter state', ['close', 'open'])]
    requestedstate: bool

    def initialize(self, state: str):
        if state.lower() == 'close':
            self.requestedstate = False
        elif state.lower() == 'open':
            self.requestedstate = True
        else:
            raise self.CommandException(f'Invalid state: {state}')
        self._connectXraySource()
        self.message.emit(f'{"Opening" if self.requestedstate else "Closing"} beam shutter.')
        self.progress.emit(f'{"Opening" if self.requestedstate else "Closing"} beam shutter.', 0, 0)
        self.xraysource().moveShutter(self.requestedstate)

    @Slot(bool, str, str)
    def onXraySourceCommandResult(self, success: bool, command: str, message: str):
        if command != 'shutter':
            logger.warning(f'Command result received for unexpected command "{command}" ({type(command)=}')
        elif not success:
            self._disconnectXraySource()
            self.fail('Shutter error.')
        else:  # success
            # wait for the shutter change
            pass

    @Slot(bool)
    def onShutter(self, state: bool):
        self._disconnectXraySource()
        if self.requestedstate == state:
            self.message.emit(f'The shutter is now {"open" if self.requestedstate else "closed"}. ')
            self.finish(state)
        else:
            self.fail(f'Cannot {"open" if self.requestedstate else "close"} the shutter.')


class Xrays(XraySourceCommand):
    name = 'xrays'
    description = 'Enable or disable X-ray generation'
    arguments = [StringChoicesArgument('state', 'Requested state', ['on', 'off'])]
    requestedstate: bool

    def initialize(self, state: str):
        if state.lower() == 'off':
            self.requestedstate = False
        elif state.lower() == 'on':
            self.requestedstate = True
        else:
            raise self.CommandException(f'Invalid state: {state}')
        self._connectXraySource()
        self.message.emit(f'Turning X-ray generator {"on" if self.requestedstate else "off"}.')
        self.progress.emit(f'Turning X-ray generator {"on" if self.requestedstate else "off"}.', 0, 0)
        if self.requestedstate:
            self.xraysource().xraysOn()
        else:
            self.xraysource().xraysOff()

    @Slot(bool, str, str)
    def onXraySourceCommandResult(self, success: bool, command: str, message: str):
        if command != 'xrays':
            logger.warning(f'Command result received for unexpected command {command}')
        if not success:
            self._disconnectXraySource()
            self.fail(f'Cannot turn X-ray generator {"on" if self.requestedstate else "off"}.')
        else:
            pass

    @Slot(str)
    def onXraySourcePowerStateChanged(self, state: str):
        self._disconnectXraySource()
        if self.requestedstate and (state == GeniX.Status.off):
            self.fail(f'Cannot turn X-ray generator on.')
        elif (not self.requestedstate) and (state != GeniX.Status.off):
            self.fail(f'Cannot turn X-ray generator off.')
        else:
            self.finish(state)


class XRayPower(XraySourceCommand):
    name = "xray_power"
    description = "Set the power of the X-ray source"
    arguments = [StringChoicesArgument('state', 'X-ray tube power state', ['off', 'standby', 'full'])]
    requestedstate: str
    commandsent: str

    def initialize(self, state: str):
        self._connectXraySource()
        try:
            if state.lower() == 'off':
                self.requestedstate = GeniX.Status.off
                self.commandsent = 'poweroff'
                self.xraysource().powerDown()
            elif state.lower() == 'standby':
                self.requestedstate = GeniX.Status.standby
                self.commandsent = 'standby'
                self.xraysource().standby()
            elif state.lower() == 'full':
                self.requestedstate = GeniX.Status.full
                self.commandsent = 'full_power'
                self.xraysource().rampup()
            else:
                raise self.CommandException(f'Invalid state: {state}')
        except:
            self._disconnectXraySource()
            raise
        self.message.emit(f'Putting X-ray source to {self.requestedstate} mode.')
        self.progress.emit(f'Putting X-ray source to {self.requestedstate} mode.', 0, 0)

    @Slot(bool, str, str)
    def onXraySourceCommandResult(self, success: bool, command: str, message: str):
        if (command == self.commandsent) and not success:
            self._disconnectXraySource()
            self.fail(f'Error while putting X-ray source power to {self.requestedstate} mode.')
        elif command != self.commandsent:
            pass
            #logger.warning(f'Command result received for unexpected command {command}')
        else:  # (command == self.commandsent) and success
            pass

    @Slot(str)
    def onXraySourcePowerStateChanged(self, state: str):
        if state == self.requestedstate:
            self.message.emit(f'X-ray generator is now in {state} mode.')
            self.finish(self.requestedstate)
        else:
            pass


class WarmUp(XraySourceCommand):
    name = 'xray_warmup'
    description = 'Start the warming-up procedure of the X-ray source'
    arguments = []

    def initialize(self):
        self._connectXraySource()
        try:
            self.message.emit('Starting X-ray source warm-up')
            self.progress.emit('X-ray source warm-up in progress...', 0, 0)
            self.xraysource().startWarmUp()
        except:
            self._disconnectXraySource()
            raise

    @Slot(str)
    def onXraySourcePowerStateChanged(self, state: str):
        if state in [GeniX.Status.off, GeniX.Status.standby]:
            self.message.emit('X-ray source warm-up finished.')
            self._disconnectXraySource()
        else:
            logger.debug(f'X-ray source power state is {state}')

    def stop(self):
        self.xraysource().stopWarmUp()
        self.xraysource().powerDown()
        super().stop()
