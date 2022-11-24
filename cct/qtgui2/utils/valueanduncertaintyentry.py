from typing import Tuple, Optional

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Signal, Slot

from .valueanduncertaintyentry_ui import Ui_Form


class ValueAndUncertaintyEntry(QtWidgets.QWidget, Ui_Form):
    valueChanged = Signal(float, float)
    maxrelativeuncertainty: float = 2  # 1 means 100%

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.uncertaintyDoubleSpinBox.setMinimum(0)
        self.uncertaintyDoubleSpinBox.setMaximum(self.valueDoubleSpinBox.maximum()*self.maxrelativeuncertainty)
        self.valueDoubleSpinBox.valueChanged.connect(self._onvaluechanged)
        self.uncertaintyDoubleSpinBox.valueChanged.connect(self._onvaluechanged)

    @Slot()
    def _onvaluechanged(self):
        self.valueChanged.emit(self.valueDoubleSpinBox.value(), self.uncertaintyDoubleSpinBox.value())

    def setMinimum(self, value: float):
        self.valueDoubleSpinBox.setMinimum(value)

    def setMaximum(self, value: float):
        self.valueDoubleSpinBox.setMaximum(value)
        self.uncertaintyDoubleSpinBox.setMaximum(value * self.maxrelativeuncertainty)

    def setDecimals(self, prec: int):
        self.valueDoubleSpinBox.setDecimals(prec)
        self.uncertaintyDoubleSpinBox.setDecimals(prec)

    def setFrame(self, showframe: bool):
        self.valueDoubleSpinBox.setFrame(showframe)
        self.uncertaintyDoubleSpinBox.setFrame(showframe)

    def setKeyboardTracking(self, kt: bool):
        self.valueDoubleSpinBox.setKeyboardTracking(kt)
        self.uncertaintyDoubleSpinBox.setKeyboardTracking(kt)

    def keyboardTracking(self):
        assert self.uncertaintyDoubleSpinBox.keyboardTracking() == self.valueDoubleSpinBox.keyboardTracking()
        return self.uncertaintyDoubleSpinBox.keyboardTracking()

    def hasFrame(self):
        assert self.uncertaintyDoubleSpinBox.hasFrame() == self.valueDoubleSpinBox.hasFrame()
        return self.uncertaintyDoubleSpinBox.hasFrame()

    def value(self) -> Tuple[float, float, int]:
        return self.valueDoubleSpinBox.value(), self.uncertaintyDoubleSpinBox.value()

    def minimum(self) -> float:
        return self.valueDoubleSpinBox.minimum()

    def maximum(self) -> float:
        return self.valueDoubleSpinBox.maximum()

    def setValue(self, value: Optional[float], uncertainty: Optional[float]):
        if value is not None:
            self.valueDoubleSpinBox.setValue(value)
        if uncertainty is not None:
            self.uncertaintyDoubleSpinBox.setValue(uncertainty)

    def setRange(self, min: float, max: float):
        self.valueDoubleSpinBox.setMinimum(min)
        self.valueDoubleSpinBox.setMaximum(max)
        self.uncertaintyDoubleSpinBox.setMaximum(max*self.maxrelativeuncertainty)
