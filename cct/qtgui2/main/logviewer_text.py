import logging

from PyQt5 import QtCore, QtWidgets, QtGui


class LogViewerText(QtWidgets.QPlainTextEdit, logging.Handler):
    def __init__(self, *args, **kwargs):
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        logging.Handler.__init__(self)
        formatter = logging.Formatter('%(asctime)s: %(levelname)s: %(name)s: %(message)s')
        self.setFormatter(formatter)
        self.debugformat = QtGui.QTextCharFormat()
        self.debugformat.setFontWeight(QtGui.QFont.Normal)
        self.debugformat.setForeground(QtCore.Qt.lightGray)
        self.warningformat = QtGui.QTextCharFormat()
        self.warningformat.setForeground(QtCore.Qt.darkYellow)
        self.errorformat = QtGui.QTextCharFormat()
        self.errorformat.setForeground(QtCore.Qt.red)
        self.criticalformat = QtGui.QTextCharFormat()
        self.criticalformat.setForeground(QtCore.Qt.black)
        self.criticalformat.setBackground(QtCore.Qt.red)
        self.infoformat = QtGui.QTextCharFormat()
        self.setReadOnly(True)

    def emit(self, record: logging.LogRecord):
        msg = self.format(record) + '\n'
        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)

        if record.levelno < logging.INFO:
            cursor.insertText(msg, self.debugformat)
        elif record.levelno < logging.WARNING:
            cursor.insertText(msg, self.infoformat)
        elif record.levelno < logging.ERROR:
            cursor.insertText(msg, self.warningformat)
        elif record.levelno < logging.CRITICAL:
            cursor.insertText(msg, self.errorformat)
        else:
            cursor.insertText(msg, self.criticalformat)
        cursor.movePosition(QtGui.QTextCursor.End)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
