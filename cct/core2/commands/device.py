from typing import Any, List
import logging

from .command import InstantCommand, CommandArgument, Command
from .commandargument import StringArgument
from ..devices.device.frontend import DeviceFrontend

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GetVar(InstantCommand):
    name="getvar"
    description = "Get the value of a device variable"
    arguments = [StringArgument('device', 'The name of the device'),
                 StringArgument('variable', 'The name of the variable')]

    def run(self, device: str, variable: str) -> Any:
        try:
            self.instrument.devicemanager[device]
        except (KeyError, IndexError):
            raise RuntimeError(f'No such device {device}')
        try:
            self.message.emit(f'{self.instrument.devicemanager[device][variable]}')
            return self.instrument.devicemanager[device][variable]
        except (KeyError, IndexError):
            raise RuntimeError(f'Device {device} has no variable named {variable}')


class DevCommand(Command):
    name = "devcommand"
    description="Execute a low-level command on a device"
    arguments=[StringArgument('device', 'The name of the device'),
               StringArgument('commandname', 'The name of the low-level command'),
               ...]
    sentcommand:str
    device: DeviceFrontend

    def _connectDevice(self):
        self.device.commandResult.connect(self.onDeviceCommandResult)

    def _disconnectDevice(self):
        self.device.commandResult.disconnect(self.onDeviceCommandResult)

    def initialize(self, device: str, commandname: str, *args):
        self.device = self.instrument.devicemanager[device]
        self._connectDevice()
        self.sentcommand = commandname
        try:
            self.device.issueCommand(commandname, args)
        except:
            self._disconnectDevice()
            raise

    def onDeviceCommandResult(self, success: bool, commandname: str, message: str):
        if commandname == self.sentcommand:
            self._disconnectDevice()
            if success:
                self.finish(message)
            else:
                self.fail(message)
        else:
            logger.warning(f'Unexpected reply: expected reply to command {self.sentcommand}, got reply to command {commandname}')


class ListVariables(InstantCommand):
    name='listvars'
    description = 'List the names of all variables of a device'
    arguments = [StringArgument('device', 'The name of the device')]

    def run(self, device: str) -> List[str]:
        self.message.emit(f'{", ".join(self.instrument.devicemanager[device].keys())}')
        return list(self.instrument.devicemanager[device].keys())