from PySide6 import QtGui, QtCore
import re
from typing import List, Tuple, Pattern

from ....core2.commands import Command


class ScriptSyntaxHighlighter(QtGui.QSyntaxHighlighter):
    formats: List[Tuple[List[Pattern], QtGui.QTextCharFormat]] = [
    ]

    def __init__(self, textdocument: QtGui.QTextDocument):
        super().__init__(textdocument)
        f = QtGui.QTextCharFormat()
        f.setFontItalic(True)
        f.setForeground(QtCore.Qt.GlobalColor.darkCyan)
        self.formats.append(([re.compile("(?P<delimiter>\"\').+(?P=delimiter)")], f))
        f = QtGui.QTextCharFormat()
        f.setFontWeight(QtGui.QFont.Bold)
        f.setForeground(QtCore.Qt.GlobalColor.darkMagenta)
        self.formats.append(([re.compile(r'\b' + c.name + r'\b') for c in Command.subclasses() if isinstance(c.name, str)], f))
        f = QtGui.QTextCharFormat()
        f.setForeground(QtCore.Qt.GlobalColor.lightGray)
        self.formats.append(([re.compile('#.*$')], f))
        f = QtGui.QTextCharFormat()
        f.setForeground(QtCore.Qt.GlobalColor.blue)
        self.formats.append(([re.compile(r'^\s*@.*$')], f))

    def highlightBlock(self, text: str) -> None:
        for regexes, textcharformat in self.formats:
            for regex in regexes:
                for m in regex.finditer(text):
                    self.setFormat(m.start(), m.end() - m.start(), textcharformat)
                    break
