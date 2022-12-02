import logging
from typing import List, Optional

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Slot

from .script import ScriptUI
from .scripting_ui import Ui_Form
from .wizard.sequencewizard import SequenceWizard
from ...utils.filebrowsers import getOpenFile
from ....core2.commands import Command
from ....core2.instrument.components.interpreter import ParsingError
from ....core2.instrument.instrument import Instrument

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Scripting(QtWidgets.QWidget, Ui_Form):
    mainwindow: "MainWindow"
    instrument: Instrument
    scripts: List[ScriptUI]
    wizard: Optional[SequenceWizard] = None

    def __init__(self, **kwargs):
        self.mainwindow = kwargs.pop('mainwindow')
        self.instrument = kwargs.pop('instrument')
        self.scripts = []
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.startStopToolButton.clicked.connect(self.startStopScript)
        self.newToolButton.clicked.connect(self.newScript)
        self.saveToolButton.clicked.connect(self.saveScript)
        self.saveAsToolButton.clicked.connect(self.saveScriptAs)
        self.loadToolButton.clicked.connect(self.openScript)
        self.wizardToolButton.clicked.connect(self.openScriptWizard)
        menu = QtWidgets.QMenu()
        menu.addAction(self.actionMeasurement_sequence_wizard)
        menu.addAction(self.actionScan_wizard)
        self.wizardToolButton.setMenu(menu)
        self.actionMeasurement_sequence_wizard.triggered.connect(self.openScriptWizard)
        self.actionScan_wizard.triggered.connect(self.openScanWizard)
        self.copyToolButton.clicked.connect(self.editCopy)
        self.cutToolButton.clicked.connect(self.editCut)
        self.pasteToolButton.clicked.connect(self.editPaste)
        self.undoToolButton.clicked.connect(self.undo)
        self.redoToolButton.clicked.connect(self.redo)
        self.tabWidget.currentChanged.connect(self.currentTabChanged)
        self.tabWidget.tabCloseRequested.connect(self.tabCloseRequested)
        QtWidgets.QApplication.clipboard().dataChanged.connect(self.onClipboardDataChanged)
        self.newScript()
        self.instrument.interpreter.scriptstarted.connect(self.onScriptStarted)
        self.instrument.interpreter.scriptfinished.connect(self.onScriptFinished)
        self.instrument.interpreter.advance.connect(self.onScriptAdvance)
        self.instrument.interpreter.message.connect(self.onScriptMessage)
        self.instrument.interpreter.flags.newFlag.connect(self.onNewFlag)
        self.instrument.interpreter.flags.flagChanged.connect(self.onFlagChanged)
        self.instrument.interpreter.flags.flagRemoved.connect(self.onFlagRemoved)
        self.flagsHorizontalLayout.addStretch(1)
        self.listWidget.clear()
        for command in sorted([c for c in Command.subclasses() if isinstance(c.name, str)], key=lambda c: c.name):
            item = QtWidgets.QListWidgetItem(command.name)
            item.setToolTip(command.helptext())
            self.listWidget.addItem(item)

    @Slot(str, bool)
    def onNewFlag(self, flagname: str, flagstate: bool):
        child = self.findChild(QtWidgets.QToolButton, f'flag_{flagname}_ToolButton')
        assert child is None
        tb = QtWidgets.QToolButton(self)
        tb.setText(flagname)
        tb.setCheckable(True)
        tb.setChecked(flagstate)
        tb.setObjectName(f'flag_{flagname}_ToolButton')
        tb.setSizePolicy(
            QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred))
        tb.toggled.connect(self.onFlagToolButtonToggled)
        self.flagsHorizontalLayout.insertWidget(self.flagsHorizontalLayout.count() - 1, tb)

    @Slot()
    def onFlagToolButtonToggled(self):
        flagname = self.sender().objectName().split('_')[1]
        self.instrument.interpreter.flags.setFlag(flagname, self.sender().isChecked())

    @Slot(str, bool)
    def onFlagChanged(self, flagname: str, flagstate: bool):
        logger.debug(f'onFlagChanged {flagname=}, {flagstate=}')
        tb: QtWidgets.QToolButton = self.findChild(QtWidgets.QToolButton, f'flag_{flagname}_ToolButton')
        tb.blockSignals(True)
        tb.setChecked(flagstate)
        tb.blockSignals(False)

    @Slot(str)
    def onFlagRemoved(self, flagname: str):
        tb = self.findChild(QtWidgets.QToolButton, f'flag_{flagname}_ToolButton')
        self.flagsHorizontalLayout.removeWidget(tb)
        tb.deleteLater()

    @Slot(str)
    def onScriptMessage(self, message: str):
        self.currentScript().addMessage(message)

    @Slot(int)
    def onScriptAdvance(self, currentline: int):
        logger.debug('onScriptAdvance')
        scriptui = self.runningScript()
        assert scriptui is not None
        scriptui.scriptEditor.highlightRunningLine(currentline)

    @Slot()
    def onScriptStarted(self):
        self.startStopToolButton.setText('Stop')
        self.startStopToolButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/stop.svg')))
        if self.currentScript() is not None:
            self.currentScript().outputPlainTextEdit.setVisible(True)
            self.currentScript().addMessage('Script started')

    @Slot(bool, str)
    def onScriptFinished(self, success: bool, message: str):
        if self.currentScript() is not None:
            if success:
                self.currentScript().addMessage(f'Script finished successfully with message "{message}".')
            else:
                self.currentScript().addMessage(f'Script failed with message "{message}".')
        self.startStopToolButton.setText('Start')
        self.startStopToolButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
        if not success:
            QtWidgets.QMessageBox.critical(self, 'Script failed', f'Script failed with message: {message}')
        sui = self.runningScript()
        if sui is not None:
            sui.scriptEditor.setReadOnly(False)
            sui.scriptEditor.highlightCurrentLine()

    @Slot()
    def onClipboardDataChanged(self):
        if self.currentScript() is not None:
            self.pasteToolButton.setEnabled(self.currentScript().canPaste())

    @Slot(int)
    def currentTabChanged(self, index: int):
        scriptui = self.currentScript()
        if scriptui is not None:
            self.undoToolButton.setEnabled(scriptui.canUndo())
            self.redoToolButton.setEnabled(scriptui.canRedo())
            self.pasteToolButton.setEnabled(scriptui.canPaste())

    @Slot(int)
    def tabCloseRequested(self, index: int):
        if self.scripts[index].isRunning():
            QtWidgets.QMessageBox.critical(self, 'Script is running', 'Cannot close the running script!')
            return
        if self.scripts[index].isModified():
            result = QtWidgets.QMessageBox.question(
                self, 'Confirm close', 'There are unsaved changes to this script. Do you want to save them?',
                buttons=QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No | QtWidgets.QMessageBox.StandardButton.Cancel)
            if result == QtWidgets.QMessageBox.StandardButton.Yes:
                self.scripts[index].save()
            elif result == QtWidgets.QMessageBox.StandardButton.Cancel:
                return
        self.tabWidget.removeTab(index)
        self.scripts[index].deleteLater()
        del self.scripts[index]

    @Slot()
    def startStopScript(self):
        if self.startStopToolButton.text() == 'Start':
            try:
                self.instrument.interpreter.parseScript(self.currentScript().text())
                self.currentScript().scriptEditor.setReadOnly(True)
            except ParsingError as pe:
                QtWidgets.QMessageBox.critical(self, 'Parsing error',
                                               f'Line {pe.args[0] + 1} is invalid. Error message: {pe.args[1]}')
                return
            except AttributeError:
                # can happen if self.currentScript() is None: then .text() will not be available
                if self.currentScript() is not None:
                    raise
            self.instrument.interpreter.execute()
        elif self.startStopToolButton.text() == 'Stop':
            self.instrument.interpreter.stop()

    @Slot()
    def openScanWizard(self):
        pass

    @Slot()
    def openScriptWizard(self):
        if self.wizard is not None:
            QtWidgets.QMessageBox.critical(self, 'Error', 'Another wizard is already open.')
            return
        self.wizard = SequenceWizard(parent=self)
        self.wizard.finished.connect(self.onWizardFinished)
        self.wizard.show()

    @Slot(int)
    def onWizardFinished(self, result: int):
        # ToDo: create script.
        logger.debug(f'Wizard finished with result {result}.')
        self.wizard.close()
        if result:
            # try to find an unmodified Untitled script
            try:
                s = [s for s in self.scripts if (not s.text().strip()) and (not s.isModified())][0]
            except IndexError:
                s = self.newScript()
            self.tabWidget.setCurrentWidget(s)
            s.scriptEditor.setPlainText(self.wizard.script())
            s.scriptEditor.document().setModified(True)
        self.wizard.deleteLater()
        self.wizard = None

    @Slot()
    def stopScriptAfterThisCommand(self):
        pass

    @Slot()
    def newScript(self) -> ScriptUI:
        s = ScriptUI()
        self._createTab(s)
        return s

    @Slot()
    def openScript(self):
        filename = getOpenFile(self, 'Load a script...', '', 'CCT script files (*.cct);;All files (*)')
        logger.debug(f'Got filename: {filename}')
        if not filename:
            return
        sui = ScriptUI()
        with open(filename, 'rt') as f:
            sui.scriptEditor.document().setPlainText(f.read())
            sui.scriptEditor.document().setModified(False)
            sui.filename = filename
        self._createTab(sui)

    @Slot()
    def saveScript(self):
        try:
            self.currentScript().save()
        except AttributeError:
            if self.currentScript() is not None:
                raise

    @Slot()
    def saveScriptAs(self):
        try:
            self.currentScript().saveas()
        except AttributeError:
            if self.currentScript() is not None:
                raise

    @Slot()
    def undo(self):
        try:
            self.currentScript().undo()
        except AttributeError:
            if self.currentScript() is not None:
                raise

    @Slot()
    def redo(self):
        try:
            self.currentScript().redo()
        except AttributeError:
            if self.currentScript() is not None:
                raise

    @Slot()
    def editCopy(self):
        try:
            self.currentScript().editCopy()
        except AttributeError:
            if self.currentScript() is not None:
                raise

    @Slot()
    def editCut(self):
        try:
            self.currentScript().editCut()
        except AttributeError:
            if self.currentScript() is not None:
                raise

    @Slot()
    def editPaste(self):
        try:
            self.currentScript().editPaste()
        except AttributeError:
            if self.currentScript() is not None:
                raise

    @Slot()
    def currentScript(self) -> Optional[ScriptUI]:
        try:
            return self.scripts[self.tabWidget.currentIndex()]
        except IndexError:
            return None

    def _createTab(self, script: ScriptUI):
        self.scripts.append(script)
        self.tabWidget.addTab(self.scripts[-1], script.getTitle())
        self.tabWidget.setCurrentIndex(len(self.scripts) - 1)
        script.modificationChanged.connect(self.onScriptModificationChanged)
        script.undoAvailable.connect(self.undoToolButton.setEnabled)
        script.redoAvailable.connect(self.redoToolButton.setEnabled)
        script.copyAvailable.connect(self.copyToolButton.setEnabled)
        script.copyAvailable.connect(self.cutToolButton.setEnabled)

    @Slot(bool)
    def onScriptModificationChanged(self, modified: bool):
        self.tabWidget.setTabText(self.scripts.index(self.sender()), self.sender().getTitle())

    def runningScript(self) -> Optional[ScriptUI]:
        try:
            return [s for s in self.scripts if s.isRunning()][0]
        except IndexError:
            return None
