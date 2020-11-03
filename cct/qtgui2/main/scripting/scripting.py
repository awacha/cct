import datetime
import logging
import os
from typing import List, Optional

from PyQt5 import QtWidgets, QtGui

from .script import ScriptUI
from .wizard.sequencewizard import SequenceWizard
from .scripting_ui import Ui_Form
from ....core2.instrument.components.interpreter import ParsingError
from ....core2.instrument.instrument import Instrument
from ....core2.commands import Command

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
        for command in sorted([c for c in Command.subclasses() if isinstance(c.name, str)], key=lambda c:c.name):
            item = QtWidgets.QListWidgetItem(command.name)
            item.setToolTip(command.helptext())
            self.listWidget.addItem(item)

    def onNewFlag(self, flagname: str, flagstate: bool):
        child = self.findChild(QtWidgets.QToolButton, f'flag_{flagname}_ToolButton')
        assert child is None
        tb = QtWidgets.QToolButton(self)
        tb.setText(flagname)
        tb.setCheckable(True)
        tb.setChecked(flagstate)
        tb.setObjectName(f'flag_{flagname}_ToolButton')
        tb.toggled.connect(self.onFlagToolButtonToggled)
        self.flagsHorizontalLayout.insertWidget(self.flagsHorizontalLayout.count() - 1, tb)

    def onFlagToolButtonToggled(self):
        flagname = self.sender().objectName().split('_')[1]
        self.instrument.interpreter.flags.setFlag(flagname, self.sender().isChecked())

    def onFlagChanged(self, flagname: str, flagstate: bool):
        logger.debug(f'onFlagChanged {flagname=}, {flagstate=}')
        tb = self.findChild(QtWidgets.QToolButton, f'flag_{flagname}_ToolButton')
        tb.blockSignals(True)
        tb.setChecked(flagstate)
        tb.blockSignals(False)

    def onFlagRemoved(self, flagname: str):
        tb = self.findChild(QtWidgets.QToolButton, f'flag_{flagname}_ToolButton')
        self.flagsHorizontalLayout.removeWidget(tb)
        tb.deleteLater()

    def onScriptMessage(self, message: str):
        self.currentScript().addMessage(message)

    def onScriptAdvance(self, currentline: int):
        logger.debug('onScriptAdvance')
        scriptui = self.runningScript()
        assert scriptui is not None
        scriptui.scriptEditor.highlightRunningLine(currentline)

    def onScriptStarted(self):
        self.startStopToolButton.setText('Stop')
        self.startStopToolButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/stop.svg')))
        self.currentScript().outputPlainTextEdit.setVisible(True)
        self.currentScript().addMessage('Script started')

    def onScriptFinished(self, success: bool, message: str):
        if success:
            self.currentScript().addMessage(f'Script finished successfully with message "{message}".')
        else:
            self.currentScript().addMessage(f'Script failed with message "{message}".')
        self.startStopToolButton.setText('Start')
        self.startStopToolButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
        if not success:
            QtWidgets.QMessageBox.critical(self, 'Script failed', f'Script failed with message: {message}')
        sui = self.runningScript()
        sui.scriptEditor.setReadOnly(False)
        sui.scriptEditor.highlightCurrentLine()

    def onClipboardDataChanged(self):
        self.pasteToolButton.setEnabled(self.currentScript().canPaste())

    def currentTabChanged(self, index: int):
        scriptui = self.currentScript()
        self.undoToolButton.setEnabled(scriptui.canUndo())
        self.redoToolButton.setEnabled(scriptui.canRedo())
        self.pasteToolButton.setEnabled(scriptui.canPaste())

    def tabCloseRequested(self, index: int):
        if self.scripts[index].isModified():
            result = QtWidgets.QMessageBox.question(
                self, 'Confirm close', 'There are unsaved changes to this script. Do you want to save them?',
                buttons=QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel)
            if result == QtWidgets.QMessageBox.Yes:
                self.scripts[index].save()
            elif result == QtWidgets.QMessageBox.Cancel:
                return
        self.tabWidget.removeTab(index)
        self.scripts[index].deleteLater()
        del self.scripts[index]

    def startStopScript(self):
        if self.startStopToolButton.text() == 'Start':
            try:
                self.instrument.interpreter.parseScript(self.currentScript().text())
                self.currentScript().scriptEditor.setReadOnly(True)
            except ParsingError as pe:
                QtWidgets.QMessageBox.critical('Parsing error',
                                               f'Line {pe.args[0] + 1} is invalid. Error message: {pe.args[1]}')
                return
            self.instrument.interpreter.execute()
        elif self.startStopToolButton.text() == 'Stop':
            self.instrument.interpreter.stop()

    def openScanWizard(self):
        pass

    def openScriptWizard(self):
        if self.wizard is not None:
            QtWidgets.QMessageBox.critical(self, 'Error', 'Another wizard is already open.')
            return
        self.wizard = SequenceWizard(parent=self)
        self.wizard.finished.connect(self.onWizardFinished)
        self.wizard.show()

    def onWizardFinished(self, result: int):
        # ToDo: create script.
        logger.debug(f'Wizard finished with result {result}.')
        self.wizard.close()
        if result:
            # try to find an unmodified Untitled script
            try:
                s = [s for s in self.scripts if (not s.text().strip()) and (not s.isModified())][0]
            except IndexError:
                s=self.newScript()
            self.tabWidget.setCurrentWidget(s)
            s.scriptEditor.setPlainText(self.wizard.script())
            s.scriptEditor.document().setModified(True)
        self.wizard.deleteLater()
        self.wizard = None

    def stopScriptAfterThisCommand(self):
        pass

    def newScript(self) -> ScriptUI:
        s=ScriptUI()
        self._createTab(s)
        return s

    def openScript(self):
        filename, filter_ = QtWidgets.QFileDialog.getOpenFileName(self, 'Load a script...', '',
                                                                  'CCT script files (*.cct);;All files (*)',
                                                                  'CCT script files (*.cct)')
        if not filename:
            return
        sui = ScriptUI()
        with open(filename, 'rt') as f:
            sui.scriptEditor.document().setPlainText(f.read())
            sui.scriptEditor.document().setModified(False)
            sui.filename = filename
        self._createTab(sui)

    def saveScript(self):
        self.currentScript().save()

    def saveScriptAs(self):
        self.currentScript().saveas()

    def undo(self):
        self.currentScript().undo()

    def redo(self):
        self.currentScript().redo()

    def editCopy(self):
        self.currentScript().editCopy()

    def editCut(self):
        self.currentScript().editCut()

    def editPaste(self):
        self.currentScript().editPaste()

    def currentScript(self) -> ScriptUI:
        return self.scripts[self.tabWidget.currentIndex()]

    def _createTab(self, script: ScriptUI):
        self.scripts.append(script)
        self.tabWidget.addTab(self.scripts[-1], 'Untitled')
        self.tabWidget.setCurrentIndex(len(self.scripts) - 1)
        script.modificationChanged.connect(self.onScriptModificationChanged)
        script.undoAvailable.connect(self.undoToolButton.setEnabled)
        script.redoAvailable.connect(self.redoToolButton.setEnabled)
        script.copyAvailable.connect(self.copyToolButton.setEnabled)
        script.copyAvailable.connect(self.cutToolButton.setEnabled)

    def onScriptModificationChanged(self, modified: bool):
        self.tabWidget.setTabText(self.scripts.index(self.sender()), self.sender().getTitle())

    def runningScript(self) -> Optional[ScriptUI]:
        try:
            return [s for s in self.scripts if s.scriptEditor.isReadOnly()][0]
        except IndexError:
            return None
