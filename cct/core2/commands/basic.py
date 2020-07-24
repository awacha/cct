"""Simple commands"""
import time

from PyQt5 import QtCore

from .command import Command


class Sleep(Command):
    name = 'sleep'
    sleeptime: float = None
    starttime: float = None

    def initialize(self, interval: float):
        if interval < 1:
            self.timerinterval = 0.1
        else:
            self.timerinterval = 0.5
        self.sleeptime = interval
        self.starttime = time.monotonic()

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        t = time.monotonic() - self.starttime
        if t >= self.sleeptime:
            self.finish(t)
        else:
            self.progress.emit(f'Sleeping for {self.sleeptime:.3g} seconds', (t / self.sleeptime) * 1000, 1000)


class Comment(Command):
    name = 'comment'
    timerinterval = 0


class Goto(Command):
    name = 'goto'
    timerinterval = 0
    targetlabel: str = ''

    def initialize(self, label: str):
        self.targetlabel = label

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        self.jump(self.targetlabel, False)


class Gosub(Command):
    name = 'gosub'
    timerinterval = 0
    targetlabel: str = ''

    def initialize(self, label: str):
        self.targetlabel = label

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        self.jump(self.targetlabel, True)


class Return(Command):
    name = 'return'
    timerinterval = 0

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        self.jump('', False)


class End(Command):
    name = 'end'
    timerinterval = 0


class Label(Command):
    name = 'label'
    timerinterval = 0
