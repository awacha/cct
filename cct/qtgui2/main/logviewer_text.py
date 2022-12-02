import logging

from PySide6 import QtCore, QtWidgets, QtGui


class LogViewerText(logging.Handler):
    widget: QtWidgets.QPlainTextEdit
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        formatter = logging.Formatter('%(asctime)s: %(levelname)s: %(name)s: %(message)s')
        self.widget = QtWidgets.QPlainTextEdit()
        self.setFormatter(formatter)
        self.debugformat = QtGui.QTextCharFormat()
        self.debugformat.setFontWeight(QtGui.QFont.Weight.Normal)
        self.debugformat.setForeground(QtCore.Qt.GlobalColor.lightGray)
        self.warningformat = QtGui.QTextCharFormat()
        self.warningformat.setForeground(QtCore.Qt.GlobalColor.darkYellow)
        self.errorformat = QtGui.QTextCharFormat()
        self.errorformat.setForeground(QtCore.Qt.GlobalColor.red)
        self.criticalformat = QtGui.QTextCharFormat()
        self.criticalformat.setForeground(QtCore.Qt.GlobalColor.black)
        self.criticalformat.setBackground(QtCore.Qt.GlobalColor.red)
        self.stronginfoformat = QtGui.QTextCharFormat()
        self.stronginfoformat.setForeground(QtCore.Qt.GlobalColor.black)
        self.stronginfoformat.setBackground(QtCore.Qt.GlobalColor.green)
        self.infoformat = QtGui.QTextCharFormat()
        self.widget.setReadOnly(True)

    def emit(self, record: logging.LogRecord):
        msg = self.format(record) + '\n'
        cursor = self.widget.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)

        if record.levelno < logging.INFO:
            cursor.insertText(msg, self.debugformat)
        elif record.levelno < logging.STRONGINFO:
            cursor.insertText(msg, self.infoformat)
        elif record.levelno < logging.WARNING:
            cursor.insertText(msg, self.stronginfoformat)
        elif record.levelno < logging.ERROR:
            cursor.insertText(msg, self.warningformat)
        elif record.levelno < logging.CRITICAL:
            cursor.insertText(msg, self.errorformat)
        else:
            cursor.insertText(msg, self.criticalformat)
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        self.widget.setTextCursor(cursor)
        self.widget.ensureCursorVisible()
