from typing import Tuple, List, Optional

from PyQt5 import QtCore, QtWidgets

from .peakeditor_ui import Ui_Dialog
from .peakmodel import PeakModel, DoubleSpinBoxDelegate


class PeakEditor(QtWidgets.QDialog, Ui_Dialog):
    peaks: List[Tuple[str, float, float]]

    def __init__(self, parent: QtWidgets.QWidget = None, peaks: Optional[List[Tuple[str, float, float]]]=None):
        super().__init__(parent)
        self.peakstore = PeakModel(peaks)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.peakstore)
        self.addPeakToolButton.clicked.connect(self.addPeak)
        self.removePeakToolButton.clicked.connect(self.removePeak)
        self.doubleSpinBoxDelegate = DoubleSpinBoxDelegate(self.treeView)
        self.treeView.setItemDelegateForColumn(1, self.doubleSpinBoxDelegate)
        self.treeView.setItemDelegateForColumn(2, self.doubleSpinBoxDelegate)

    def addPeak(self):
        self.peakstore.insertRow(self.peakstore.rowCount(), QtCore.QModelIndex())

    def removePeak(self):
        current = self.treeView.selectionModel().currentIndex()
        if current.isValid():
            self.peakstore.removeRow(current.row(), QtCore.QModelIndex())

    def peaks(self):
        return self.peakstore.toList()
