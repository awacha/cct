# coding: utf-8
"""A method for updating a combo box"""
from typing import List

from .blocksignalscontextmanager import SignalsBlocked
from PySide6 import QtWidgets


def updateComboBox(combobox: QtWidgets.QComboBox, newitems: List[str]) -> bool:
    """Replace all items in a combo box, keeping the current selection if possible.

    No signals are emitted from the combo box.

    :param combobox: the combo box to update
    :type combobox: QtWidgets.QComboBox
    :param newitems: list of the new items
    :type newitems: list of strings
    :return: True if the current selection needed to be changed, False if not
    """
    oldcurrent = combobox.currentText() if combobox.currentIndex() >= 0 else None
    with SignalsBlocked(combobox):
        combobox.clear()
        combobox.addItems(newitems)
        if oldcurrent is None:
            return True
        else:
            newindexforoldcurrent = combobox.findText(oldcurrent)
            if newindexforoldcurrent < 0:
                return True
            else:
                combobox.setCurrentIndex(newindexforoldcurrent)
                return False
