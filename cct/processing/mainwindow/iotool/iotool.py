import os
import pickle
import re
from configparser import ConfigParser
from typing import List, Tuple

import appdirs
from PyQt5 import QtWidgets, QtCore

from .fsnrangemodel import FSNRangeModel
from .iotool_ui import Ui_Form
from ..toolbase import ToolBase, HeaderModel


class IoTool(ToolBase, Ui_Form):
    _default_config = {
        'path': {
            'prefixes': {
                'crd': 'crd',
            },
            'directories': {
                'mask': 'mask',
                'eval2d': 'eval2d',
                'images': 'images',
                'param': 'param',
            },
            'fsndigits': 5,
        },
        'datareduction': {
            'absintrefname': 'Glassy_Carbon',
        },
    }
    h5NameChanged = QtCore.pyqtSignal(str)
    newHeaderModel = QtCore.pyqtSignal(HeaderModel)
    exportFolderChanged = QtCore.pyqtSignal(str)
    cctConfigChanged = QtCore.pyqtSignal(dict)
    projectfilename = None

    def setupUi(self, Form):
        super().setupUi(Form)
        self.header_columns = HeaderModel.visiblecolumns
        self.badFSNListFileNameLineEdit.setText(
            os.path.normpath(os.path.join(appdirs.user_state_dir('cpt', 'CREDO', roaming=True), 'badfsns')))
        self.browseBadFSNListFileNamePushButton.clicked.connect(self.onBrowseBadFSNListFileName)
        self.browseHDFPushButton.clicked.connect(self.onBrowseSaveFile)
        self.browsePushButton.clicked.connect(self.onBrowseRootDir)
        self.reloadPushButton.clicked.connect(self.reloadHeaders)
        self.browseExportFolderPushButton.clicked.connect(self.onBrowseExportFolder)
        self.ioProgressBar.setVisible(False)
        self.configWidgets = [
            (self.badFSNListFileNameLineEdit, 'io', 'badfsnsfile'),
            (self.saveHDFLineEdit, 'io', 'hdf5'),
            (self.rootDirLineEdit, 'io', 'datadir'),
            (self.exportFolderLineEdit, 'export', 'folder'),
        ]
        self.addToListPushButton.clicked.connect(self.addFSNRange)
        self.removeFromListPushButton.clicked.connect(self.removeFSNRange)
        self.clearListPushButton.clicked.connect(self.clearFSNRanges)
        self.fsnList = FSNRangeModel()
        self.fsnListTreeView.setModel(self.fsnList)

    def addFSNRange(self):
        self.fsnList.addRange(0, 0)

    def removeFSNRange(self):
        while self.fsnListTreeView.selectedIndexes():
            sel = self.fsnListTreeView.selectedIndexes()
            self.fsnList.removeRow(sel[0].row(), QtCore.QModelIndex())

    def clearFSNRanges(self):
        self.fsnList.clear()

    def onUiStyleChange(self):
        QtWidgets.QApplication.instance().setStyle(self.uiStyleComboBox.currentText())

    def onBrowseExportFolder(self):
        filename = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select the folder to output files to...')
        if filename:
            self.exportFolderLineEdit.setText(os.path.normpath(filename))
            self.exportFolderChanged.emit(os.path.normpath(filename))

    def fsnRanges(self) -> List[Tuple[int, int]]:
        return self.fsnList.getRanges()

    def reloadHeaders(self):
        try:
            self.busy.emit(True)
            self.statusBar.showMessage('Loading headers, please wait...')
            if ((self.headerModel is not None) and
                    (self.headerModel.rootdir == self.rootdir) and
                    (self.headerModel.badfsnsfile == self.badFSNListFileNameLineEdit.text()) and
                    (self.headerModel.prefix == self.cctConfig['path']['prefixes']['crd'])):
                self.newheadermodel = self.headerModel
                self.newheadermodel.fsnranges = self.fsnRanges()
            else:
                self.newheadermodel = HeaderModel(
                    self,
                    self.rootdir,
                    self.cctConfig['path']['prefixes']['crd'],
                    self.fsnRanges(),
                    self.header_columns,
                    self.badFSNListFileNameLineEdit.text()
                )
                self.newheadermodel.fsnloaded.connect(self.onHeaderModelFSNLoaded)
            self.newheadermodel.reloadHeaders()
        except:
            self.busy.emit(False)
            self.statusBar.clearMessage()
            raise

    def setRootDir(self, rootdir: str):
        self.rootdir = rootdir
        configfile = os.path.join(self.rootdir, 'config', 'cct.pickle')
        try:
            with open(configfile, 'rb') as f:
                self.cctConfigChanged.emit(pickle.load(f))
        except FileNotFoundError:
            QtWidgets.QMessageBox.warning(self, 'Error while loading config file',
                                          'Error while loading config file: {} not found. Using a default config.'.format(
                                              configfile))
            self.cctConfigChanged.emit(self._default_config)
            return False
        except pickle.PickleError:
            QtWidgets.QMessageBox.critical(self, 'Error while loading config file',
                                           'Error while loading config file: {} is malformed'.format(configfile))
            return False
        self.reloadPushButton.setEnabled(True)
        self.rootDirLineEdit.setText(os.path.normpath(rootdir))
        return True

    def onBrowseRootDir(self):
        filename = QtWidgets.QFileDialog.getExistingDirectory(self, 'Open CREDO data directory')
        if filename:
            self.setRootDir(filename)

    def setHDF5File(self, filename):
        self.saveHDFLineEdit.setText(os.path.normpath(filename))
        self.h5NameChanged.emit(filename)

    def onBrowseSaveFile(self):
        filename, fltr = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save processed results to...', '',
            'HDF5 files (*.h5 *.hdf5);;All files (*)',
            'HDF5 files (*.h5 *.hdf5)')
        if not filename:
            return
        if not filename.endswith('.h5') and not filename.endswith('.hdf5'):
            filename = filename + '.h5'
        self.setHDF5File(filename)

    def onBrowseBadFSNListFileName(self):
        filename, fltr = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Select bad FSN list file...', '',
            'Text files (*.txt *.dat);;All files (*)',
            'Text files (*.txt *.dat)')
        if not filename:
            return
        if not filename.endswith('.txt') and not filename.endswith('.dat'):
            filename = filename + '.txt'
        self.setBadFSNFile(filename)

    def setBadFSNFile(self, filename):
        self.badFSNListFileNameLineEdit.setText(os.path.normpath(filename))
        try:
            self.headermodel.setBadFSNFile(filename)
        except AttributeError:
            pass

    def load_state(self, config: ConfigParser):
        super().load_state(config)
        try:
            self.fsnList.clear()
            for left, right in re.findall('\(\s*(\d+),\s*(\d+)\)', config['io']['fsnranges']):
                self.fsnList.addRange(int(left), int(right))
        except KeyError:
            pass
        if self.rootDirLineEdit.text():
            self.setRootDir(self.rootDirLineEdit.text())
        if self.saveHDFLineEdit.text():
            self.setHDF5File(self.saveHDFLineEdit.text())
        try:
            self.header_columns = config['headerview']['fields'].split(';')
        except KeyError:
            pass
        self.exportFolderChanged.emit(self.exportFolderLineEdit.text())
        try:
            self.projectfilename = config['io']['projectfilename']
        except KeyError:
            pass
        if not self.projectfilename:
            self.projectfilename = None

    def save_state(self, config: ConfigParser):
        super().save_state(config)
        config['headerview'] = {}
        config['headerview']['fields'] = ';'.join(self.header_columns)
        config['io']['fsnranges'] = '[' + ', '.join(
            ['({}, {})'.format(left, right) for left, right in self.fsnRanges()]) + ']'
        config['io']['projectfilename'] = self.projectfilename if self.projectfilename is not None else ''

    def onHeaderModelFSNLoaded(self, totalcount, currentcount, thisfsn):
        if totalcount == currentcount == thisfsn == 0:
            self.ioProgressBar.setVisible(False)
            self.busy.emit(False)
            self.newHeaderModel.emit(self.newheadermodel)
        else:
            if totalcount > 0 and not self.ioProgressBar.isVisible():
                self.busy.emit(True)
                self.ioProgressBar.setVisible(True)
                self.ioProgressBar.setMinimum(0)
                self.ioProgressBar.setMaximum(totalcount)
                self.ioProgressBar.setFormat('Loading headers...')
            self.ioProgressBar.setValue(currentcount)

    def saveProject(self):
        if self.projectfilename is None:
            return
        cp = ConfigParser()
        for sibling in self.siblings:
            self.siblings[sibling].save_state(cp)
        with open(self.projectfilename, 'wt') as f:
            cp.write(f)
        self.updateRecents(self.projectfilename)

    def updateRecents(self, projectfilename=None):
        if projectfilename is None:
            projectfilename = self.projectfilename
        if not projectfilename:
            return
        try:
            with open(os.path.join(appdirs.user_config_dir('cpt', 'CREDO', roaming=True), 'projecthistory'), 'rt') as f:
                recentprojects = [l.strip() for l in f if l.strip().lower().endswith('.cpt')]
        except FileNotFoundError:
            recentprojects = []
        if projectfilename not in recentprojects:
            recentprojects.append(projectfilename)
        with open(os.path.join(appdirs.user_config_dir('cpt', 'CREDO', roaming=True), 'projecthistory'), 'wt') as f:
            for pf in sorted(recentprojects):
                f.write(pf + '\n')

    def loadProject(self, projectfilename: str):
        if not projectfilename:
            return
        cp = ConfigParser()
        cp.read(projectfilename)
        for sibling in self.siblings:
            self.siblings[sibling].load_state(cp)
        self.projectfilename = projectfilename
        self.projectNameLineEdit.setText(self.projectfilename)
        self.updateRecents(self.projectfilename)

    def autosaveProject(self):
        self.saveProject()
