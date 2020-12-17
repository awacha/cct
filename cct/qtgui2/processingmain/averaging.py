import logging
import multiprocessing

from PyQt5 import QtWidgets, QtGui
from .averaging_ui import Ui_Form
from .processingwindow import ProcessingWindow

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AveragingWindow(ProcessingWindow, Ui_Form):
    def setupUi(self, Form):
        super().setupUi(Form)
        self.treeView.setModel(self.project.summarization)
        self.runPushButton.clicked.connect(self.runClicked)
        self.project.summarization.started.connect(self.onAveragingStarted)
        self.project.summarization.finished.connect(self.onAveragingStopped)
        self.project.summarization.progress.connect(self.onProgress)
        self.progressBar.setVisible(False)
        self.treeView.model().modelReset.connect(self.resizeTreeViewColumns)
        self.processCountSpinBox.setValue(self.project.summarization.maxprocesscount)
        self.processCountSpinBox.valueChanged.connect(self.onProcessCountChanged)
        self.processCountSpinBox.setMinimum(1)
        self.processCountSpinBox.setMaximum(multiprocessing.cpu_count())

    def onProcessCountChanged(self, value: int):
        if self.project.summarization.isBusy():
            raise ValueError('Cannot change process count: summarization is busy.')
        else:
            self.project.summarization.maxprocesscount = value

    def resizeTreeViewColumns(self):
        logger.debug('Resizing treeview columns of averaging window')
        for c in range(self.treeView.model().columnCount()):
            self.treeView.resizeColumnToContents(c)
        logger.debug('Resized treeview columns of averaging window.')

    def runClicked(self):
        if self.runPushButton.text() == 'Run':
            self.project.summarization.start()
        else:
            self.project.summarization.stop()

    def onAveragingStarted(self):
        self.runPushButton.setText('Stop')
        self.runPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/stop.svg')))
        self.progressBar.setVisible(True)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)
        self.processCountSpinBox.setEnabled(False)

    def onAveragingStopped(self, success: bool):
        self.processCountSpinBox.setEnabled(True)
        self.runPushButton.setText('Run')
        self.runPushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
        self.progressBar.setVisible(False)
        if not success:
            QtWidgets.QMessageBox.critical(self, 'Averaging stopped', 'Averaging stopped unexpectedly.')
        else:
            badfsnstext = '\n'.join([f'  {sd.samplename}: {", ".join([str(f) for f in sorted(sd.lastfoundbadfsns)])}' for sd in self.project.summarization if sd.lastfoundbadfsns])
            QtWidgets.QMessageBox.information(
                self, 'Averaging finished',
                'Finished averaging images.' + (f" New bad exposures found: \n{badfsnstext}" if badfsnstext else " No new bad exposures found.")
            )

    def onProgress(self, current: int, total: int):
        logger.debug(f'Averaging progress: {current=}, {total=}')
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(current)
