from enum import Enum
from typing import Sequence, List

from PySide6 import QtWidgets, QtCore

from .spacerselector_ui import Ui_Dialog


class SpacerSelectorDialog(QtWidgets.QDialog, Ui_Dialog):
    class TargetTypes(Enum):
        L1= 1
        L2=2
        FlightPipes=3

    spacers: List[float]
    title: str
    target: TargetTypes


    def __init__(self, parent, availablespacers: Sequence[float], currentspacers: Sequence[float], target: TargetTypes):
        super().__init__(parent, QtCore.Qt.WindowType.Dialog)
        self.spacers = sorted(availablespacers)
        self.target = target
        self.setupUi(self)
        for s in currentspacers:
            item= [i for i in self.listWidget.findItems(f'{s:.0f}', QtCore.Qt.MatchFlag.MatchExactly) if not i.isSelected()][0]
            item.setSelected(True)

    def setupUi(self, Dialog):
        super().setupUi(Dialog)
        if self.target == self.TargetTypes.L1:
            self.label.setText('Select spacers between pinholes #1 and #2')
        elif self.target == self.TargetTypes.L2:
            self.label.setText('Select spacers between pinholes #2 and #3')
        elif self.target == self.TargetTypes.FlightPipes:
            self.label.setText('Select flight pipes')
        self.listWidget.addItems([f'{x:.0f}' for x in self.spacers])

    def selectedSpacers(self) -> List[float]:
        return [self.spacers[index.row()] for index in self.listWidget.selectedIndexes()]