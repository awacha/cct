# coding = utf-8
"""Commands for the peristaltic pump"""
import math
from typing import Optional, Any
from PySide6 import QtCore
from PySide6.QtCore import Signal, Slot

import time
import logging

from .command import Command, InstantCommand
from .commandargument import FloatArgument, StringArgument, IntArgument
from ..devices.peristalticpump.leadfluid.frontend import BT100S, ControlMode

logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class PeristalticPumpDispense(Command):
    name = 'pp_dispense_wait'
    description = 'Drive the peristaltic pump for the desired time, wait until completed'
    arguments = [FloatArgument('dispensetime', 'Dispense time in seconds', defaultvalue=None),
                 StringArgument('direction', 'Rotation direction (clockwise or counterclockwise)', defaultvalue=None),
                 FloatArgument('speed', 'Rotation speed (rpm)', defaultvalue=None),
                 ]
    starttime: Optional[float] = None
    timerinterval = 0.1
    clockwise: Optional[bool]
    dispensetime: Optional[float]
    speed: Optional[float]
    wait_until_complete: bool = True

    def initialize(self, dispensetime: Optional[float], direction: Optional[str], speed: Optional[float]):
        logger.debug(f'Initializing pp_dispense command (variant: {self.name}): {dispensetime=}, {direction=}, {speed=}')
        try:
            self.device()
        except IndexError:
            raise self.CommandException('No peristaltic pump found!')
        self.dispensetime = dispensetime
        if direction is None:
            self.clockwise = None
        elif direction.lower() == 'clockwise':
            self.clockwise = True
        elif direction.lower() == 'counterclockwise':
            self.clockwise = False
        else:
            raise self.CommandException('Invalid value for argument `direction`: '
                                        'must be either "clockwise" or "counterclockwise".')
        self.speed = speed
        self.device().commandResult.connect(self.onCommandResult)
        if dispensetime is None:
            logger.debug('Skipping setting dispense time: default requested')
            self.onCommandResult(True, 'set_dispense_time', None)
        elif math.isfinite(dispensetime):
            logger.debug(f'Setting dispense time to {dispensetime:.1f} sec')
            self.device().setDispenseTime(dispensetime)
        else:
            logger.debug('Skipping setting dispense time: infinite')
            self.onCommandResult(True, 'set_dispense_time', None)
            pass  # continuous operation requested, do not set dispense time.
        self.starttime = None

    def finalize(self):
        logger.debug(f'Finalizing command {self.name}')
        self.device().commandResult.disconnect(self.onCommandResult)

    def device(self) -> BT100S:
        return self.instrument.devicemanager.peristalticpump()

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        if self.starttime is None:
            self.progress.emit('Initializing peristaltic pump...', 0, 0)
        else:
            disptime = self.device()['dispense_time']
            elapsed = time.monotonic() - self.starttime
            if (elapsed > disptime) and (not self.device()['running']):
                # dispense time elapsed and the pump is not running anymore => we are finished
                self.finish(True)
            else:
                self.progress.emit(
                    f'Dispensing for {disptime:.1f} seconds, '
                    f'{disptime - elapsed:.1f} seconds remaining',
                    int(1000 * elapsed / disptime), 1000
                )

    def stop(self):
        self.device().stopRotation()
        self.fail('User stop')

    @Slot(bool, str, object)
    def onCommandResult(self, success: bool, command: str, result: Any):
        logger.debug(f'Command result from peristaltic pump: {success=}, {command=}, {result=}')
        if not success:
            self.fail(f'Peristaltic pump command {command} failed.')
        elif command == 'set_dispense_time':
            if self.clockwise is None:
                self.onCommandResult(True, 'clockwise', None)
            else:
                self.device().setClockwise(self.clockwise)
        elif (command == 'clockwise') or (command == 'counterclockwise'):
            if self.speed is None:
                self.onCommandResult(True, 'setspeed', None)
            else:
                self.device().setRotationSpeed(self.speed)
        elif (command == 'setspeed'):
            if (self.dispensetime is None) or math.isfinite(self.dispensetime):
                # finite dispense mode
                self.device().setControlMode(ControlMode.Foot_Switch)
            else:
                assert not math.isfinite(self.dispensetime)
                # infinite dispense mode
                self.device().setControlMode(ControlMode.Internal)
        elif (command == 'footswitch_control') or (command == 'internal_control'):
            self.device().startRotation()
        elif (command == 'start'):
            self.message.emit(
                f'Peristaltic pump running {self.device()["direction"]} at {self.device()["rotating_speed"]:.1f} rpm ' + (
                    f'for {self.device()["dispense_time"]:.1f} seconds.' if (
                            self.device()["control_mode"] == ControlMode.Foot_Switch.value) else "until stopped.")
            )
            if (not self.wait_until_complete) or (
                    (self.dispensetime is not None) and (not math.isfinite(self.dispensetime))):
                self.finish(True)
            else:
                self.starttime = time.monotonic()


class PeristalticPumpDispenseNowait(PeristalticPumpDispense):
    name = 'pp_dispense_start'
    description = 'Drive the peristaltic pump for the desired time, do not wait until completed'
    wait_until_complete: bool = False


class PeristalticPumpStart(PeristalticPumpDispense):
    name = 'pp_start'
    description = 'Start the peristaltic pump'
    arguments = [StringArgument('direction', 'Rotation direction (clockwise or counterclockwise)', defaultvalue=None),
                 FloatArgument('speed', 'Rotation speed (rpm)', defaultvalue=None),
                 ]
    wait_until_complete = False

    def initialize(self, direction: Optional[str], speed: Optional[float]):
        return super().initialize(math.inf, direction, speed)


class PeristalticPumpStop(Command):
    name = 'pp_stop'
    description = 'Stop the peristaltic pump'
    arguments=[]

    def initialize(self, *args: Any):
        try:
            self.device()
        except IndexError:
            raise self.CommandException('No peristaltic pump found!')
        self.device().commandResult.connect(self.onCommandResult)
        self.device().stopRotation()

    def finalize(self):
        self.device().commandResult.disconnect(self.onCommandResult)

    def device(self) -> BT100S:
        return self.instrument.devicemanager.peristalticpump()

    @Slot(bool, str, object)
    def onCommandResult(self, success: bool, command: str, result: Any):
        if not success:
            self.fail(f'Peristaltic pump command {command} failed.')
        elif command == 'stop':
            self.message.emit('Peristaltic pump stopped.')
            self.finish(True)
