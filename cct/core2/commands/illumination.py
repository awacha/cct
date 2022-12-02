# coding = utf-8
from typing import Any
from PySide6.QtCore import Slot

import logging

from .command import Command
from .commandargument import IntArgument
from ..devices.illumination.schott import KL2500LED

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class IlluminationSetBrightness(Command):
    name = 'set_illumination_brightness'
    description = 'Set the brightness of the sample illumination source'
    arguments = [IntArgument('brightness', 'Brightness level of the source', defaultvalue=None),
                 ]

    def initialize(self, brightness: float):
        try:
            self.device().commandResult.connect(self.onCommandResult)
        except IndexError:
            raise self.CommandException('No illumination source found!')
        try:
            self.device().setBrightness(brightness)
        except ValueError as ve:
            raise self.CommandException(*ve.args)

    def device(self) -> KL2500LED:
        dev = self.instrument.devicemanager.getByDeviceName('KL2500LED')
        assert isinstance(dev, KL2500LED)
        return dev

    @Slot(bool, str, object)
    def onCommandResult(self, success: bool, command: str, result: Any):
        if command != 'set_brightness':
            return
        if not success:
            self.fail(f'Cannot set illumination brightness.')
        else:
            self.finish(True)
