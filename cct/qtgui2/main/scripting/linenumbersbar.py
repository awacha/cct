from PyQt5 import QtWidgets, QtCore, QtGui


class LineNumbersBar(QtWidgets.QWidget):
    codeeditor: QtWidgets.QPlainTextEdit

    def __init__(self, parent: QtWidgets.QPlainTextEdit):
        self.codeeditor = parent
        super().__init__(parent)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self.codeeditor.linenumbersbarAreaWidth())

    def paintEvent(self, a0: QtGui.QPaintEvent) -> None:
        return self.codeeditor.linenumbersbarPaintEvent(a0)

