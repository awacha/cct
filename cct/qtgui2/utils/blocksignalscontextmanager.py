# coding: utf-8

"""A context manager to block signals on Qt wigets or simple objects"""
from typing import List, Tuple, Sequence

from PyQt5 import QtCore

class SignalsBlocked:
    """A context manager to block signals on Qt objects

    Typical usage:

    with SignalsBlocked(object1, object2, ...):
        ... do something ...

    """
    objects: Sequence[QtCore.QObject]

    def __init__(self, *objects: QtCore.QObject):
        self.objects = objects

    def __enter__(self):
        for obj in self.objects:
            obj.blockSignals(True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        for obj in self.objects:
            obj.blockSignals(False)
