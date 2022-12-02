import datetime
import logging
import os
from typing import Optional

from PySide6 import QtWidgets
from PySide6.QtCore import Signal

from .script_ui import Ui_Form
from .scripteditor import ScriptEditor
from .syntaxhighlighter import ScriptSyntaxHighlighter
from ...utils.filebrowsers import getSaveFile

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ScriptUI(QtWidgets.QWidget, Ui_Form):
    modificationChanged = Signal(bool)
    undoAvailable = Signal(bool)
    redoAvailable = Signal(bool)
    copyAvailable = Signal(bool)
    filename: Optional[str] = None
    scriptEditor: ScriptEditor
    syntaxhighlighter: ScriptSyntaxHighlighter

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.scriptEditor = ScriptEditor(self.splitter)
        self.scriptEditorVerticalLayout.addWidget(self.scriptEditor)
        self.scriptEditor.setSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self.splitter.setSizes([2 * self.splitter.width() // 3, self.splitter.width() // 3])
        self.scriptEditor.document().modificationChanged.connect(self.modificationChanged)
        self.scriptEditor.undoAvailable.connect(self.undoAvailable)
        self.scriptEditor.redoAvailable.connect(self.redoAvailable)
        self.scriptEditor.copyAvailable.connect(self.copyAvailable)
        self.outputPlainTextEdit.hide()
        self.syntaxhighlighter = ScriptSyntaxHighlighter(self.scriptEditor.document())

    def undo(self):
        self.scriptEditor.undo()

    def redo(self):
        self.scriptEditor.redo()

    def editCut(self):
        self.scriptEditor.cut()

    def editPaste(self):
        self.scriptEditor.paste()

    def editCopy(self):
        self.scriptEditor.copy()

    def canPaste(self):
        return self.scriptEditor.canPaste()

    def canUndo(self):
        return self.scriptEditor.document().isUndoAvailable()

    def canRedo(self):
        return self.scriptEditor.document().isRedoAvailable()

    def isModified(self) -> bool:
        return self.scriptEditor.document().isModified()

    def save(self):
        if self.filename is None:
            self.saveas()
        else:
            with open(self.filename, 'wt') as f:
                f.write(self.scriptEditor.document().toPlainText())
            self.scriptEditor.document().setModified(False)
            self.modificationChanged.emit(False)
        logger.info(f'Script saved to {self.filename}')

    def saveas(self):
        filename = getSaveFile(self, 'Save script to file', '', 'CCT script files (*.cct);;All files (*)',
                               defaultsuffix='.cct')
        logger.debug(f'Got filename: {filename}')
        if not filename:
            return
        logger.debug(f'Setting filename {filename}')
        self.filename = filename
        logger.debug('Saving...')
        self.save()

    def getTitle(self) -> str:
        if self.filename is None:
            return 'Untitled' + (' *' if self.isModified() else '')
        else:
            return os.path.split(self.filename)[-1] + (' *' if self.isModified() else '')

    def text(self) -> str:
        return self.scriptEditor.toPlainText()

    def addMessage(self, message: str):
        self.outputPlainTextEdit.appendPlainText(f'{datetime.datetime.now()}: {message.strip()}')
        self.outputPlainTextEdit.ensureCursorVisible()
        if self.filename is not None:
            with open(os.path.splitext(self.filename)[0] + '.log', 'a') as f:
                f.write(f'{datetime.datetime.now()}: {message.strip()}\n')

    def isRunning(self) -> bool:
        return self.scriptEditor.isReadOnly()
