import logging
import os
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from PyQt5 import QtCore, QtWidgets, QtGui

from .scripteditor_ui import Ui_MainWindow
from ...core.mixins import ToolWindow
from ....core.commands import Command
from ....core.services.interpreter import Interpreter
from ....core.commands.script import Script


class HighLighter(QtGui.QSyntaxHighlighter):
    def __init__(self, *args, **kwargs):
        QtGui.QSyntaxHighlighter.__init__(self, *args, **kwargs)
        self.keywordformat = QtGui.QTextCharFormat()
        self.keywordformat.setFontWeight(QtGui.QFont.Bold)
        self.keywordformat.setForeground(QtCore.Qt.darkMagenta)
        self.keywords_re = [re.compile('\\b' + c.name + '\\b') for c in Command.allcommands()]

    def highlightBlock(self, text: str):
        for kw in self.keywords_re:
            for match in kw.finditer(text):
                self.setFormat(match.start(), match.end(), self.keywordformat)


class ScriptEditor(QtWidgets.QMainWindow, Ui_MainWindow, ToolWindow):
    def __init__(self, *args, **kwargs):
        credo = kwargs.pop('credo')
        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)
        self.setupToolWindow(credo)
        self.lastfilename = None
        self.setupUi(self)

    def setupUi(self, MainWindow):
        Ui_MainWindow.setupUi(self, MainWindow)
        self.flags = {}
        for i in range(10):
            self.flags[i] = self.toolBarFlags.addAction(str(i), lambda i=i: self.flagtoggled(i))
            self.flags[i].setCheckable(True)
        self.document = self.scriptEdit.document()
        assert isinstance(self.document, QtGui.QTextDocument)
        self.document.undoAvailable.connect(self.actionUndo.setEnabled)
        self.document.redoAvailable.connect(self.actionRedo.setEnabled)
        self.actionUndo.triggered.connect(self.document.undo)
        self.actionRedo.triggered.connect(self.document.redo)
        self.actionUndo.setEnabled(False)
        self.actionRedo.setEnabled(False)
        self.scriptEdit.copyAvailable.connect(self.actionCopy.setEnabled)
        self.scriptEdit.copyAvailable.connect(self.actionCut.setEnabled)
        self.scriptEdit.copyAvailable.connect(self.actionDelete.setEnabled)
        self.actionCut.triggered.connect(self.scriptEdit.cut)
        self.actionCopy.triggered.connect(self.scriptEdit.copy)
        self.actionPaste.triggered.connect(self.scriptEdit.paste)
        self.actionCopy.setEnabled(False)
        self.actionCut.setEnabled(False)
        self.actionDelete.setEnabled(False)
        self.document.setDefaultFont(QtGui.QFont('monospace'))
        textopts = QtGui.QTextOption()
        textopts.setFlags(
            QtGui.QTextOption.IncludeTrailingSpaces | QtGui.QTextOption.ShowTabsAndSpaces | QtGui.QTextOption.ShowLineAndParagraphSeparators)
        textopts.setAlignment(QtCore.Qt.AlignLeft)
        self.scriptEdit.setTabStopWidth(4)
        self.document.setDefaultTextOption(textopts)
        self.document.modificationChanged.connect(self.scriptModificationStateChanged)
        self.actionSave_script.setEnabled(False)
        self.actionSave_script.triggered.connect(self.saveScript)
        self.actionNew_script.triggered.connect(self.newScript)
        self.actionLoad_script.triggered.connect(self.loadScript)
        self.actionStart.triggered.connect(self.runScript)
        self.actionPause.triggered.connect(self.pauseScript)
        self.syntaxHighLighter = HighLighter(self.document)
        self._currentline = QtGui.QTextCursor(self.document)

    def flagtoggled(self, flagnumber):
        print('Flag #{} is now {}'.format(flagnumber, self.flags[flagnumber].isChecked()))

    def scriptModificationStateChanged(self, modified):
        self.actionSave_script.setEnabled(modified)

    def saveScript(self):
        if self.lastfilename is None:
            return self.saveAsScript()
        try:
            with open(self.lastfilename, 'wt') as f:
                assert isinstance(self.document, QtGui.QTextDocument)
                f.write(self.document.toPlainText())
        except PermissionError:
            QtWidgets.QMessageBox.critical(self, 'Error', 'Cannot open file {}'.format(self.lastfilename))
            return
        self.document.setModified(False)

    def newScript(self):
        if self.confirmDropChanges():
            self.document.setPlainText('')
            self.document.setModified(False)

    def saveAsScript(self):
        if self.lastfilename is None:
            if self.credo is not None:
                path = os.path.join(
                    os.getcwd(), self.credo.config['path']['directories']['scripts'])
            else:
                path = os.getcwd()
        else:
            path = os.path.split(self.lastfilename)
        self.lastfilename, filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Save script to file", path, '*.cct')
        return self.saveScript()

    def loadScript(self):
        if self.lastfilename is None:
            if self.credo is not None:
                path = os.path.join(
                    os.getcwd(), self.credo.config['path']['directories']['scripts'])
            else:
                path = os.getcwd()
        else:
            path = os.path.split(self.lastfilename)
        if self.confirmDropChanges():
            filename, filter = QtWidgets.QFileDialog.getOpenFileName(
                self, "Open a script file", path, '*.cct')
            try:
                with open(filename, 'rt') as f:
                    text = ''.join(f.readlines())
            except (PermissionError, FileNotFoundError):
                QtWidgets.QMessageBox.critical(self, 'Error', 'Cannot open file {}'.format(self.lastfilename))
                return
            assert isinstance(self.document, QtGui.QTextDocument)
            self.document.setPlainText(text)
            self.lastfilename = filename
            self.document.setModified(False)

    def setIdle(self):
        self.scriptEdit.setReadOnly(False)
        self.scriptEdit.setExtraSelections([])
        super().setIdle()

    def setBusy(self):
        self.scriptEdit.setReadOnly(True)
        super().setBusy()

    def runScript(self):
        self.setBusy()
        self.executeCommand(Script, script=self.scriptEdit.document().toPlainText())

    def pauseScript(self):
        pass

    def confirmDropChanges(self):
        """Present a confirmation dialog before abandoning changes to the script.
        Saving the script is ensured by this function, if the user requests it by
        clicking the 'YES' button.

        Returns:
            True if the operation abandoning the changes can commence (YES or NO has been
                pressed), or
            False if the changes should be kept intact (CANCEL is pressed or the window has
                been closed).
        """
        assert isinstance(self.document, QtGui.QTextDocument)
        if self.document.isModified():
            result = QtWidgets.QMessageBox.question(
                self, "Save changed script?",
                "The script has been changed since it has been last saved. Would you like to save it now?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel)
            if result in [QtWidgets.QMessageBox.Yes]:
                self.saveScript()
            elif result in [QtWidgets.QMessageBox.Escape, QtWidgets.QMessageBox.Cancel]:
                return False
            return True
        return True

    def onCmdDetail(self, interpreter: Interpreter, cmdname: str, detail):
        assert isinstance(detail, tuple)
        if detail[0] == 'cmd-start':
            self.onCommandStarted(detail[1])
        elif detail[0] == 'paused':
            self.onScriptPaused()

    def onCommandStarted(self, linenumber: int):
        logger.debug('Command started on line {:d}'.format(linenumber))
        es = QtWidgets.QTextEdit.ExtraSelection()
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(QtGui.QBrush(QtCore.Qt.green))
        es.format = fmt
        cursor = QtGui.QTextCursor(self.document)
        cursor.movePosition(QtGui.QTextCursor.Start)
        cursor.movePosition(QtGui.QTextCursor.Down, QtGui.QTextCursor.MoveAnchor, linenumber)
        cursor.movePosition(QtGui.QTextCursor.StartOfLine, QtGui.QTextCursor.MoveAnchor)
        cursor.movePosition(QtGui.QTextCursor.EndOfLine, QtGui.QTextCursor.KeepAnchor)
        cursor.select(QtGui.QTextCursor.LineUnderCursor)
        es.cursor = cursor
        self.scriptEdit.setExtraSelections([es])

    def onCmdReturn(self, interpreter: Interpreter, cmdname: str, retval):
        super().onCmdReturn(interpreter, cmdname, retval)
        self.setIdle()

    def onScriptPaused(self):
        pass
