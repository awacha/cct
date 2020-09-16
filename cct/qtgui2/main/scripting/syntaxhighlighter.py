from PyQt5 import QtGui, QtCore
import re
from typing import List, Tuple, Pattern

from ....core2.commands import Command


class ScriptSyntaxHighlighter(QtGui.QSyntaxHighlighter):
    formats: List[Tuple[List[Pattern], QtGui.QTextCharFormat]] = [
    ]

    def __init__(self, textdocument: QtGui.QTextDocument):
        super().__init__(textdocument)
        f = QtGui.QTextCharFormat()
        f.setFontWeight(QtGui.QFont.Bold)
        f.setForeground(QtCore.Qt.darkMagenta)
        self.formats.append(([re.compile(r'\b' + c.name + r'\b') for c in Command.subclasses()], f))
        f = QtGui.QTextCharFormat()
        f.setForeground(QtCore.Qt.lightGray)
        self.formats.append(([re.compile('#.*$')], f))
        f = QtGui.QTextCharFormat()
        f.setForeground(QtCore.Qt.blue)
        self.formats.append(([re.compile(r'^\s*@.*$')], f))

    def highlightBlock(self, text: str) -> None:
        for regexes, textcharformat in self.formats:
            for regex in regexes:
                for m in regex.finditer(text):
                    self.setFormat(m.start(), m.end() - m.start(), textcharformat)
