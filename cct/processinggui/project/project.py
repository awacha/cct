import logging
import os
from typing import Optional, Any, Union

import numpy as np
from PyQt5 import QtCore, QtWidgets, QtGui
from sastool.io.credo_cct import Exposure, Header

from .headerloader import HeaderLoader
from .project_ui import Ui_projectWindow
from ..config import Config
from ..models.fsnranges import FSNRangeModel
from ..models.headerlist import HeaderList
from ...core.processing.loader import Loader

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class Project(QtWidgets.QWidget, Ui_projectWindow):
    config:Config = None
    idleChanged = QtCore.pyqtSignal(bool, name='idleChanged')
    exposureToBeShown = QtCore.pyqtSignal(Exposure, name='exposureToBeShown')
    idle: bool=True
    headerLoader: HeaderLoader=Optional[None]
    headerList: HeaderList=None
    _loader: Loader=None

    def __init__(self, parent:QtWidgets.QMainWindow):
        super().__init__(parent)
        self.config = Config()
        self.config.configItemChanged.connect(self.onConfigChanged)
        self.headerList = HeaderList(self.config)
        logger.debug('Before instantiating a Loader with datadir "{}"'.format(self.config.datadir))
        self._loader = Loader(self.config.datadir)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.fsnRangesModel = FSNRangeModel()
        self.treeView.setModel(self.fsnRangesModel)
        self.setWindowTitle('*Untitled*')
        self.progressBar.hide()
        self.idleChanged.connect(self.onIdleChanged)

    def closeEvent(self, event:QtGui.QCloseEvent):
        logger.debug('Project window received a closeEvent.')
        if not self.confirmSave():
            logger.debug('Ignoring closeEvent')
            event.ignore()
        else:
            logger.debug('Accepting closeEvent')
            event.accept()
#            self.destroy()
#            self.deleteLater()

    def confirmSave(self):
        """Ask the user if she wants to save the changes.

        :returns: True if it is safe to proceed (user chose to save or to discard) and False if it is not
        """
        if not self.isWindowModified():
            return True
        result = QtWidgets.QMessageBox.question(
                self.window(), 'Confirm close',
                'The current project has unsaved changes. Do you want to save them now?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.Yes
        )
        if result == QtWidgets.QMessageBox.Cancel:
            return False
        elif result == QtWidgets.QMessageBox.Yes:
            return self.save() # returns False if it is not saved
        else:
            assert result == QtWidgets.QMessageBox.No
            return True

    @QtCore.pyqtSlot()
    def on_addPushButton_clicked(self):
        self.fsnRangesModel.add(0, 0)

    @QtCore.pyqtSlot()
    def on_removePushButton_clicked(self):
        try:
            self.fsRangesModel.removeRow(self.treeView.selectionModel().selectedRows(0)[0].row())
        except IndexError:
            return

    @QtCore.pyqtSlot()
    def on_rootDirToolButton_clicked(self):
        dirname = QtWidgets.QFileDialog.getExistingDirectory(
                self, 'Select a CCT root directory', '')
        self.rootDirLineEdit.setText(dirname)

    @QtCore.pyqtSlot()
    def on_badFSNsToolButton_clicked(self):
        filename, filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Select file to write bad FSNs in...",
            '', 'ASCII text files (*.txt);;All files (*)', 'ASCII text files (*.txt)'
        )
        if not filename:
            return
        if not filename.upper().endswith('.TXT'):
            filename+='.txt'
        self.badFSNsLineEdit.setText(filename)

    @QtCore.pyqtSlot()
    def on_hdf5FileToolButton_clicked(self):
        filename, filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Select file to write results in...",
            '', 'Hierachical Data Format v5 (*.h5);;All files (*)', 'Hierarchical Data Format v5 (*.h5)'
        )
        if not filename:
            return
        if not filename.upper().endswith('.H5'):
            filename+='.h5'
        self.hdf5FileLineEdit.setText(filename)

    @QtCore.pyqtSlot()
    def on_rootDirLineEdit_textChanged(self):
        self.config.datadir = self.rootDirLineEdit.text()
        self.setWindowModified(True)

    @QtCore.pyqtSlot()
    def on_badFSNsLineEdit_textChanged(self):
        self.config.badfsnsfile = self.badFSNsLineEdit.text()
        self.setWindowModified(True)

    @QtCore.pyqtSlot()
    def on_hdf5FileLineEdit_textChanged(self):
        self.config.hdf5 = self.hdf5FileLineEdit.text()
        self.setWindowModified()

    def save(self) -> bool:
        if not self.window().windowFilePath():
            return self.saveAs()
        assert self.window().windowFilePath()
        self.toConfig()
        self.config.save(self.window().windowFilePath())
        self.setWindowModified(True)
        return True

    def saveAs(self, filename:Optional[str]=None) -> bool:
        filename, filter_ = QtWidgets.QFileDialog.getSaveFileName(
                self.window(), 'Save current project as...', filename if filename is None else '',
                'CPT project files (*.cpt2);;All files (*)', 'CPT project files (*.cpt2)'
        )
        if not filename:
            return False
        else:
            if not filename.lower().endswith('.cpt2'):
                filename = filename + '.cpt2'
            self.window().setWindowFilePath(filename)
            self.setWindowTitle(os.path.split(filename)[-1])
            return self.save()

    def open(self, filename:Optional[str]=None):
        if filename is None:
            filename, filter_ = QtWidgets.QFileDialog.getOpenFileName(
                    self.window(), 'Load project from...', '',
                    'CPT project files (*.cpt2);;All files (*)',
                    'CPT project files (*.cpt2)'
            )
            if not filename:
                return False
        self.config.load(filename)
        self.fromConfig()
        self.setWindowTitle(os.path.split(filename)[-1])
        self.window().setWindowFilePath(filename)
        self.setWindowModified(False)

    def setIdle(self, idle:bool):
        self.idle = idle
        self.idleChanged.emit(self.idle)

    def _startReload(self):
        if not self.idle:
            raise RuntimeError('Reload process is already running')
        self.setIdle(False)
        self.progressBar.show()
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)
        self.progressBar.setFormat('Loading headers...')
        self.reloadPushButton.setText('Stop')
        self.reloadPushButton.setIcon(QtGui.QIcon.fromTheme('process-stop'))
        self.reloadPushButton.setEnabled(True)
        self.headerLoader = HeaderLoader(self.fsnRangesModel.fsns(), [os.path.join(self.config.datadir, 'eval2d')], 'crd_{:05d}.pickle')
        self.headerLoader.finished.connect(self.onHeaderLoadingFinished)
        self.headerLoader.progress.connect(self.onHeaderLoadingProgress)
        self.headerLoader.submit()

    def _finishReload(self):
        """Clean up the GUI after the reloading process finished."""
        if self.idle:
            raise RuntimeError('Reload process is not running')
        self.progressBar.hide()
        self.reloadPushButton.setText('Reload')
        self.reloadPushButton.setIcon(QtGui.QIcon.fromTheme('view-refresh'))
        self.setIdle(True)

    def reloadHeaders(self):
        if self.reloadPushButton.text() == 'Stop':
            self.headerLoader.stop()
        else:
            self._startReload()

    def onHeaderLoadingFinished(self):
        assert self.headerLoader is not None
        assert self.headerLoader is not None
        self.headerList.replaceAllHeaders(self.headerLoader.headers())
        self.headerLoader.deleteLater()
        self.headerLoader = None
        self._finishReload()

    def onHeaderLoadingProgress(self, total:int, done:int):
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(done)
        self.progressBar.setFormat('Loading headers {}/{}...'.format(done, total))

    def process(self):
        #ToDo
        pass

    @QtCore.pyqtSlot()
    def on_reloadPushButton_clicked(self):
        self.reloadHeaders()

    @QtCore.pyqtSlot()
    def on_processPushButton_clicked(self):
        self.process()

    def toConfig(self):
        self.config.datadir = self.rootDirLineEdit.text()
        self.config.badfsnsfile = self.badFSNsLineEdit.text()
        self.config.hdf5 = self.hdf5FileLineEdit.text()
        self.config.fsnranges = self.fsnRangesModel.toList()

    def fromConfig(self):
        self.rootDirLineEdit.setText(self.config.datadir)
        self.badFSNsLineEdit.setText(self.config.badfsnsfile)
        self.hdf5FileLineEdit.setText(self.config.hdf5)
        self.fsnRangesModel.fromList(self.config.fsnranges)

    def onConfigChanged(self, section:str, itemname:str, newvalue: Any):
        if itemname == 'datadir':
            logger.debug('Root directory changed to "{}"'.format(newvalue))
            self._loader = Loader(newvalue)
        self.setWindowModified(True)

    def onIdleChanged(self, isidle: bool):
        logger.debug('IdleChanged callback running')
        for widget in [self.rootDirLineEdit, self.rootDirToolButton, self.badFSNsLineEdit, self.badFSNsToolButton,
                       self.hdf5FileLineEdit, self.hdf5FileLineEdit, self.treeView, self.addPushButton,
                       self.removePushButton, self.reloadPushButton, self.processPushButton]:
            widget.setEnabled(isidle)

    def loadHeader(self, fsn:int) -> Header:
        return self._loader.loadHeader(fsn)

    def loadMask(self, maskname:str) -> np.ndarray:
        return self._loader.loadMask(maskname)

    def loadExposure(self, fsnorheader:Union[int, Header]) -> Exposure:
        if isinstance(fsnorheader, int):
            return self._loader.loadExposure(fsnorheader)
        elif isinstance(fsnorheader, Header):
            return self._loader.loadExposure(fsnorheader.fsn)
        else:
            raise ValueError('Invalid type for argument `fsnorheader`: {}'.format(type(fsnorheader)))


