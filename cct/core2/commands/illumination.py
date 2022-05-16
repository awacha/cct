# coding = utf-8
"""Commands for the Schott KL2500LED light source"""
import math
from typing import Optional, Any
from PyQt5 import QtCore
import time
import logging

from .command import Command, InstantCommand
from .commandargument import FloatArgument, StringArgument, IntArgument
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
        dev = [d for d in self.instrument.devicemanager if d.devicename == 'KL2500LED'][0]
        assert isinstance(dev, KL2500LED)
        return dev

    def onCommandResult(self, success: bool, command: str, result: Any):
        if command != 'set_brightness':
            return
        if not success:
            self.fail(f'Cannot set illumination brightness.')
        else:
            self.finish(True)
