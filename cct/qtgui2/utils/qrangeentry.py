from typing import Tuple, Optional

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Signal, Slot

from .qrangeentry_ui import Ui_Form


class QRangeEntry(QtWidgets.QWidget, Ui_Form):
    valueChanged = Signal(float, float, int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.qminDoubleSpinBox.valueChanged.connect(self.qmaxDoubleSpinBox.setMinimum)
        self.qmaxDoubleSpinBox.valueChanged.connect(self.qminDoubleSpinBox.setMaximum)
        self.qminDoubleSpinBox.valueChanged.connect(self._onvaluechanged)
        self.qmaxDoubleSpinBox.valueChanged.connect(self._onvaluechanged)
        self.qCountSpinBox.valueChanged.connect(self._onvaluechanged)

    @Slot()
    def _onvaluechanged(self):
        self.valueChanged.emit(self.qminDoubleSpinBox.value(), self.qmaxDoubleSpinBox.value(), self.qCountSpinBox.value())

    def setMinimum(self, value: float):
        self.qminDoubleSpinBox.setMinimum(value)

    def setMaximum(self, value: float):
        self.qmaxDoubleSpinBox.setMaximum(value)

    def setDecimals(self, prec: int):
        self.qminDoubleSpinBox.setDecimals(prec)
        self.qmaxDoubleSpinBox.setDecimals(prec)

    def setFrame(self, showframe: bool):
        self.qminDoubleSpinBox.setFrame(showframe)
        self.qmaxDoubleSpinBox.setFrame(showframe)
        self.qCountSpinBox.setFrame(showframe)

    def setKeyboardTracking(self, kt: bool):
        self.qminDoubleSpinBox.setKeyboardTracking(kt)
        self.qmaxDoubleSpinBox.setKeyboardTracking(kt)
        self.qCountSpinBox.setKeyboardTracking(kt)

    def keyboardTracking(self):
        assert self.qmaxDoubleSpinBox.keyboardTracking() == self.qminDoubleSpinBox.keyboardTracking() == self.qCountSpinBox.keyboardTracking()
        return self.qmaxDoubleSpinBox.keyboardTracking()

    def hasFrame(self):
        assert self.qmaxDoubleSpinBox.hasFrame() == self.qminDoubleSpinBox.hasFrame() == self.qCountSpinBox.hasFrame()
        return self.qmaxDoubleSpinBox.hasFrame()

    def value(self) -> Tuple[float, float, int]:
        return self.qminDoubleSpinBox.value(), self.qmaxDoubleSpinBox.value(), self.qCountSpinBox.value()

    def minimum(self) -> float:
        return self.qminDoubleSpinBox.minimum()

    def maximum(self) -> float:
        return self.qmaxDoubleSpinBox.maximum()

    def setValue(self, qmin: Optional[float], qmax: Optional[float], count: Optional[int]):
        if qmin is not None:
            self.qminDoubleSpinBox.setValue(qmin)
        if qmax is not None:
            self.qmaxDoubleSpinBox.setValue(qmax)
        if count is not None:
            self.qCountSpinBox.setValue(count)

    def setRange(self, min: float, max: float):
        self.qminDoubleSpinBox.setMinimum(min)
        self.qmaxDoubleSpinBox.setMaximum(max)
