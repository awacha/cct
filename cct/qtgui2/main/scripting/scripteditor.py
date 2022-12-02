import logging
import math
from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Slot

from .linenumbersbar import LineNumbersBar

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ScriptEditor(QtWidgets.QPlainTextEdit):
    linenumbersbar: LineNumbersBar
    lastRunCursor: Optional[QtGui.QTextCursor] = None

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.lastRunCursor = None
        self.linenumbersbar = LineNumbersBar(self)
        self.blockCountChanged.connect(self.updateLineNumbersBarAreaWidth)
        self.updateRequest.connect(self.updateLineNumbersBar)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.document().setDefaultFont(QtGui.QFont('monospace', 12))
        self.updateLineNumbersBarAreaWidth(0)
        self.highlightCurrentLine()

    def linenumbersbarPaintEvent(self, paintevent: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self.linenumbersbar)
        painter.fillRect(paintevent.rect(), QtCore.Qt.GlobalColor.lightGray)
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        if self.isReadOnly():
            thisblocknumber = self.lastRunCursor.blockNumber()
        else:
            thisblocknumber = self.textCursor().blockNumber()
        while block.isValid() and (top <= paintevent.rect().bottom()):
            if block.isVisible() and (bottom >= paintevent.rect().top()):
                painter.setPen(QtCore.Qt.GlobalColor.black)
                painter.drawText(0, top, self.linenumbersbar.width(), self.fontMetrics().height(), QtCore.Qt.AlignmentFlag.AlignRight,
                                 str(block.blockNumber() + 1))
                if (block.blockNumber() == thisblocknumber) and self.isReadOnly():
                    img = QtGui.QIcon.fromTheme('media-playback-start').pixmap(
                        QtCore.QSize(self.fontMetrics().height(), self.fontMetrics().height())).toImage()
                    painter.drawImage(QtCore.QRect(0, top, self.fontMetrics().height(), self.fontMetrics().height()),
                                      img)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

    def linenumbersbarAreaWidth(self) -> int:
        digits = int(math.log10(max(1, self.blockCount()))) + 1
        return 3 + self.fontMetrics().height() + self.fontMetrics().boundingRect('9').width() * digits

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        cr = self.contentsRect()
        self.linenumbersbar.setGeometry(QtCore.QRect(cr.left(), cr.top(), self.linenumbersbarAreaWidth(), cr.height()))
        super().resizeEvent(event)

    @Slot(int)
    def updateLineNumbersBarAreaWidth(self, blockcount: int):
        self.setViewportMargins(self.linenumbersbarAreaWidth(), 0, 0, 0)

    @Slot()
    def highlightCurrentLine(self):
        if self.isReadOnly():
            return
        selection = QtWidgets.QTextEdit.ExtraSelection()
        color = QtGui.QColor(QtCore.Qt.GlobalColor.yellow).lighter(160)
        selection.format.setBackground(color)
        selection.format.setForeground(QtGui.QColor('black'))
        selection.format.setProperty(QtGui.QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = QtGui.QTextCursor(self.textCursor())
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    @Slot(QtCore.QRect, int)
    def updateLineNumbersBar(self, rect: QtCore.QRect, dy: int):
        if dy:
            self.linenumbersbar.scroll(0, dy)
        else:
            self.linenumbersbar.update(0, rect.y(), self.linenumbersbar.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumbersBarAreaWidth(0)

    @Slot(int)
    def highlightRunningLine(self, line: int):
        selection = QtWidgets.QTextEdit.ExtraSelection()
        color = QtGui.QColor(QtCore.Qt.GlobalColor.green).lighter(160)
        selection.format.setBackground(color)
        selection.format.setForeground(QtGui.QColor('black'))
        selection.format.setProperty(QtGui.QTextFormat.Property.FullWidthSelection, True)
        self.lastRunCursor = QtGui.QTextCursor(self.document().findBlockByNumber(line))
        selection.cursor = self.lastRunCursor
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
