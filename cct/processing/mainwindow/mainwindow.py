import inspect
import os
import pickle

from PyQt5 import QtWidgets, QtCore
from sastool.io.credo_cct.header import Header

from .headerpopup import HeaderPopup
from .mainwindow_ui import Ui_MainWindow
from ..headermodel import HeaderModel


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self, None)
        self.rootdir=None
        self.setupUi(self)
        self.setRootDir('/mnt/credo_data/2017')

    def setupUi(self, MainWindow:QtWidgets.QMainWindow):
        Ui_MainWindow.setupUi(self, MainWindow)
        self.browseHDFPushButton.clicked.connect(self.onBrowseSaveFile)
        self.browsePushButton.clicked.connect(self.onBrowseRootDir)
        self.processPushButton.clicked.connect(self.onProcess)
        self.reloadPushButton.clicked.connect(self.onReload)
        self.headersTreeView.header().setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.headersTreeView.header().customContextMenuRequested.connect(self.onHeaderViewHeaderContextMenu)

    def resizeHeaderViewColumns(self):
        for i in range(self.headermodel.columnCount()):
            self.headersTreeView.resizeColumnToContents(i)

    def onHeaderViewHeaderContextMenu(self, position:QtCore.QPoint):
        print('onHeaderViewHeaderContextMenu')
        self.headerpopup=HeaderPopup(
            self, self.headermodel.visiblecolumns,
            sorted([x[0] for x in inspect.getmembers(Header) if isinstance(x[1],property)]))
        self.headerpopup.applied.connect(self.onHeaderPopupApplied)
        self.headerpopup.show()
        self.headerpopup.move(self.mapToGlobal(position))
        self.headerpopup.closed.connect(self.onHeaderPopupDestroyed)
        self.resizeHeaderViewColumns()

    def onHeaderPopupDestroyed(self):
        print('Header popup destroyed')
        del self.headerpopup

    def onHeaderPopupApplied(self):
        print('onHeaderPopupApplied')
        self.headermodel.visiblecolumns=self.headerpopup.fields
        self.headermodel.reloadHeaders()

    def onReload(self):
        newheadermodel = HeaderModel(self, self.rootdir, self.config['path']['prefixes']['crd'], self.firstFSNSpinBox.value(), self.lastFSNSpinBox.value())
        self.headersTreeView.setModel(newheadermodel)
        if hasattr(self, 'headermodel'):
            self.headermodel.cleanup()
            del self.headermodel
        self.headermodel=newheadermodel
        self.resizeHeaderViewColumns()

    def onProcess(self):
        pass

    def setRootDir(self, rootdir:str):
        self.rootdir = rootdir
        configfile = os.path.join(self.rootdir, 'config', 'cct.pickle')
        try:
            with open(configfile, 'rb') as f:
                self.config=pickle.load(f)
        except FileNotFoundError:
            QtWidgets.QMessageBox.critical(self, 'Error while loading config file','Error while loading config file: {} not found.'.format(configfile))
            return False
        except pickle.PickleError:
            QtWidgets.QMessageBox.critical(self, 'Error while loading config file','Error while loading config file: {} is malformed'.format(configfile))
            return False
        self.firstFSNSpinBox.setEnabled(True)
        self.lastFSNSpinBox.setEnabled(True)
        self.reloadPushButton.setEnabled(True)
        self.rootDirLineEdit.setText(rootdir)
        return True

    def onBrowseRootDir(self):
        filename = QtWidgets.QFileDialog.getExistingDirectory(self, 'Open CREDO data directory')
        print(filename)
        if filename:
            self.setRootDir(filename)

    def onBrowseSaveFile(self):
        filename, filter = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save processed results to...','',
            'HDF5 files (*.h5 *.hdf5);;All files (*)',
            'HDF5 files (*.h5 *.hdf5)')
        if filename is None:
            return
        if not filename.endswith('.h5') and not filename.endswith('.hdf5'):
            filename=filename+'.h5'
        self.saveHDFLineEdit.setText(filename)
        self.processPushButton.setEnabled(True)

