from typing import Optional

from PyQt5 import QtWidgets


def browseMask(parentwidget: QtWidgets.QWidget) -> Optional[str]:
    filename, filter_ = QtWidgets.QFileDialog.getOpenFileName(
        parentwidget, 'Select a mask file', '', 'Mask files (*.mat *.npy);;All files (*)', 'Mask files (*.mat *.npy)')
    if not filename:
        return None
    return filename
