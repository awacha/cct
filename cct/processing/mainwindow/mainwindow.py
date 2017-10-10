import inspect
import multiprocessing
import multiprocessing.queues
import os
import pickle
import queue
from typing import Iterable

import h5py
from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from sastool.io.credo_cct.header import Header

from .headerpopup import HeaderPopup
from .mainwindow_ui import Ui_MainWindow
from ..display.correlmatrix import show_cmatrix
from ..display.outlier_test import display_outlier_test_results
from ..display.show_image import show_scattering_image
from ..display.summarize_curves import summarize_curves
from ..export_table import export_table
from ..headermodel import HeaderModel
from ...core.processing.summarize import Summarizer
from ...core.utils.timeout import IdleFunction


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self, None)
        self.rootdir=None
        self.processingprocess = None
        self.idlefcn = None
        self.setupUi(self)
        self.setRootDir('/mnt/credo_data/2017')
        self.firstFSNSpinBox.setValue(0)
        self.lastFSNSpinBox.setValue(100)
        self.reloadPushButton.click()
        self.saveHDFLineEdit.setText('test.h5')
        self.processPushButton.setEnabled(True)
        self.updateResults()

    def setupUi(self, MainWindow:QtWidgets.QMainWindow):
        Ui_MainWindow.setupUi(self, MainWindow)
        self.browseHDFPushButton.clicked.connect(self.onBrowseSaveFile)
        self.browsePushButton.clicked.connect(self.onBrowseRootDir)
        self.processPushButton.clicked.connect(self.onProcess)
        self.reloadPushButton.clicked.connect(self.onReload)
        self.headersTreeView.header().setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.headersTreeView.header().customContextMenuRequested.connect(self.onHeaderViewHeaderContextMenu)
        self.resultsDistanceSelectorComboBox.setEnabled(False)
        self.resultsSampleSelectorComboBox.setEnabled(False)
        self.resultsSampleSelectorComboBox.currentIndexChanged.connect(self.onResultsSampleSelected)
        self.resultsDistanceSelectorComboBox.currentIndexChanged.connect(self.onResultsDistanceSelected)
        self.plotCorMatPushButton.setEnabled(False)
        self.plotCorMatTestResultsPushButton.setEnabled(False)
        self.plotCurvesPushButton.setEnabled(False)
        self.plotImagePushButton.setEnabled(False)
        self.progressGroupBox.setVisible(False)
        self.plotCorMatTestResultsPushButton.clicked.connect(self.onPlotCorMatResults)
        self.plotCorMatPushButton.clicked.connect(self.onPlotCorMat)
        self.plotCurvesPushButton.clicked.connect(self.onPlotCurves)
        self.plotImagePushButton.clicked.connect(self.onPlotImage)
        self.figure=Figure()
        self.canvas=FigureCanvasQTAgg(self.figure)
        vl=QtWidgets.QVBoxLayout(self.figureContainerWidget)
        vl.addWidget(self.canvas)
        self.figuretoolbar=NavigationToolbar2QT(self.canvas, self.figureContainerWidget)
        vl.addWidget(self.figuretoolbar)
        self.exportHeaderTablePushButton.clicked.connect(self.onExportHeadersTable)
        self.exportTablePushButton.clicked.connect(self.onExportTable)

    def onExportHeadersTable(self):
        fname, filter = QtWidgets.QFileDialog.getSaveFileName(self, 'Write table to file...','','MS Excel 2007-2016 files (*.xlsx, *.xlsm);;MS Excel files (*.xls);;All files (*)',
                                              'MS Excel 2007-2016 files (*.xlsx, *.xlsm)')
        if not fname:
            return
        export_table(fname, self.headermodel)

    def onExportTable(self):
        fname, filter = QtWidgets.QFileDialog.getSaveFileName(self, 'Write table to file...','','MS Excel 2007-2016 files (*.xlsx, *.xlsm);;MS Excel files (*.xls);;All files (*)',
                                              'MS Excel 2007-2016 files (*.xlsx, *.xlsm)')
        if not fname:
            return
        export_table(fname, self.treeView.model())


    def onPlotCorMat(self):
        with h5py.File(self.saveHDFLineEdit.text(), 'r') as f:
            show_cmatrix(self.figure, f['Samples'][self.resultsSampleSelectorComboBox.currentText()][self.resultsDistanceSelectorComboBox.currentText()])
        self.canvas.draw()
        self.tabWidget.setCurrentWidget(self.figureContainerWidget)

    def onPlotCorMatResults(self):
        with h5py.File(self.saveHDFLineEdit.text(),'r') as f:
            model=display_outlier_test_results(f['Samples'][self.resultsSampleSelectorComboBox.currentText()][self.resultsDistanceSelectorComboBox.currentText()]['curves'])
            self.treeView.setModel(model)
            for c in range(model.columnCount()):
                self.treeView.resizeColumnToContents(c)
        self.tabWidget.setCurrentWidget(self.tableContainerWidget)

    def onPlotCurves(self):
        with h5py.File(self.saveHDFLineEdit.text(),'r') as f:
            summarize_curves(self.figure, f['Samples'][self.resultsSampleSelectorComboBox.currentText()][self.resultsDistanceSelectorComboBox.currentText()]['curves'])
        self.canvas.draw()
        self.tabWidget.setCurrentWidget(self.figureContainerWidget)

    def onPlotImage(self):
        with h5py.File(self.saveHDFLineEdit.text(), 'r') as f:
            show_scattering_image(self.figure, f['Samples'][self.resultsSampleSelectorComboBox.currentText()][self.resultsDistanceSelectorComboBox.currentText()])
        self.canvas.draw()
        self.tabWidget.setCurrentWidget(self.figureContainerWidget)

    def onResultsSampleSelected(self):
        if not len(self.resultsSampleSelectorComboBox):
            return
        try:
            with h5py.File(self.saveHDFLineEdit.text(),'r') as f:
                self.resultsDistanceSelectorComboBox.clear()
                self.resultsDistanceSelectorComboBox.addItems(
                    sorted(f['Samples'][self.resultsSampleSelectorComboBox.currentText()],
                           key=lambda x:float(x)))
                self.resultsDistanceSelectorComboBox.setCurrentIndex(0)
        except FileNotFoundError:
            return

    def onResultsDistanceSelected(self):
        self.plotImagePushButton.setEnabled(self.resultsDistanceSelectorComboBox.currentIndex()>=0)
        self.plotCurvesPushButton.setEnabled(self.resultsDistanceSelectorComboBox.currentIndex()>=0)
        self.plotCorMatPushButton.setEnabled(self.resultsDistanceSelectorComboBox.currentIndex()>=0)
        self.plotCorMatTestResultsPushButton.setEnabled(self.resultsDistanceSelectorComboBox.currentIndex()>=0)

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
        self.queue = multiprocessing.Queue()
        kwargs={
            'fsns':range(self.firstFSNSpinBox.value(), self.lastFSNSpinBox.value()+1),
            'exppath':self.headermodel.eval2d_pathes,
            'parampath':self.headermodel.eval2d_pathes,
            'maskpath':self.headermodel.mask_pathes,
            'outputfile':self.saveHDFLineEdit.text(),
            'prefix':self.config['path']['prefixes']['crd'],
            'ndigits':self.config['path']['fsndigits'],
            'errorpropagation':self.errorPropagationComboBox.currentIndex(),
            'abscissaerrorpropagation':self.abscissaErrorPropagationComboBox.currentIndex(),
            'sanitize_curves':self.sanitizeCurvesCheckBox.isChecked(),
            'logarithmic_correlmatrix':self.logarithmicCorrelMatrixCheckBox.isChecked(),
            'std_multiplier':self.stdMultiplierDoubleSpinBox.value(),
            'queue': self.queue,
        }
        self.processingprocess = multiprocessing.Process(target=self.do_processing, name='Summarization', kwargs=kwargs)
        self.idlefcn = IdleFunction(self.check_processing_progress, 100)
        self.processingprocess.start()
        self.progressGroupBox.setVisible(True)


    def do_processing(self, queue:multiprocessing.queues.Queue,
                      fsns:Iterable[int], exppath:Iterable[str], parampath:Iterable[str], maskpath:Iterable[str],
                      outputfile:str, prefix:str, ndigits:int, errorpropagation:int, abscissaerrorpropagation:int,
                      sanitize_curves:bool, logarithmic_correlmatrix:bool, std_multiplier:int,):
        s = Summarizer(fsns, exppath, parampath, maskpath, outputfile, prefix, ndigits, errorpropagation,
                       abscissaerrorpropagation, sanitize_curves, logarithmic_correlmatrix, std_multiplier)
        queue.put_nowait(('__init_loadheaders__',len(fsns)))
        for msg1, msg2 in s.load_headers(yield_messages=True):
            queue.put_nowait((msg1, msg2))
        for msg1, msg2 in s.summarize(True, yield_messages=True):
            queue.put_nowait((msg1, msg2))
        queue.put_nowait(('__done__', None))
        return True

    def check_processing_progress(self):
        if self.processingprocess is None:
            self.idlefcn = None
            self.queue = None
            return False
        try:
            assert isinstance(self.queue, multiprocessing.queues.Queue)
            msg1, msg2=self.queue.get_nowait()
            if msg1 == '__init_summarize__':
                assert isinstance(msg2, int) # msg2 is the number of samples times the number of distances
                self.progressBar1.setMinimum(0)
                self.progressBar1.setMaximum(msg2)
                self.progressbar1StatusLabel.setText('')
                self.progressbar1TitleLabel.setText('Processed sample:')
                self.progressbar2TitleLabel.setText('Processed exposure:')
                self.progressBar2.setMinimum(0)
                self.progressBar2.setMaximum(0)
                self.progressBar2.setVisible(True)
                self.progressbar2TitleLabel.setVisible(True)
                self.progressbar2StatusLabel.setVisible(True)
            elif msg1 == '__init_loadheaders__':
                assert isinstance(msg2, int) # the number of headers to load
                self.progressBar2.setVisible(False)
                self.progressbar2StatusLabel.setVisible(False)
                self.progressbar2TitleLabel.setVisible(False)
                self.progressbar1TitleLabel.setText('Loaded header:')
                self.progressbar1StatusLabel.setText('')
                self.progressBar1.setMinimum(0)
                self.progressBar1.setMaximum(msg2)
                self.progressBar1.setValue(0)
            elif msg1 in ['__header_loaded__', '__header_notfound__']:
                # loaded a header for FSN
                assert isinstance(msg2, int) # msg2 is the FSN of the header just loaded or not found.
                self.progressBar1.setValue(msg2)
                self.progressbar1StatusLabel.setText('{:d}'.format(msg2))
            elif msg1 in ['__exposure_loaded__', '__exposure_notfound__']:
                self.progressBar2.setValue(self.progressBar2.value()+1)
                self.progressbar2StatusLabel.setText('{:d}'.format(msg2))
            elif msg1 == '__init_collect_exposures__':
                self.progressbar2TitleLabel.setText('Processed exposure:')
                self.progressbar2StatusLabel.setText('')
                self.progressBar2.setMinimum(0)
                self.progressBar2.setMaximum(msg2)
            elif msg1 == '__init_stabilityassessment__':
                self.progressBar2.setMinimum(0)
                self.progressBar2.setMaximum(0)
                self.progressbar2StatusLabel.setText('')
                self.progressbar2TitleLabel.setText('Stability assessment...')
            elif msg1 == '__done__':
                self.processingprocess.join()
                self.processingprocess=None
                self.progressGroupBox.setVisible(False)
                self.idlefcn.stop()
                self.idlefcn=None
                self.updateResults()
                return False
            elif msg1.startswith('__'):
                pass
            else:
                assert isinstance(msg1, str) # sample
                assert isinstance(msg2, float) # distance
                self.progressBar1.setValue(self.progressBar1.value()+1)
                self.progressbar1StatusLabel.setText('{} ({:.2f} mm)'.format(msg1, msg2))
        except queue.Empty:
            return True
        return True


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
        self.updateResults()

    def updateResults(self):
        try:
            with h5py.File(self.saveHDFLineEdit.text(), 'r') as f:
                samples=sorted(f['Samples'].keys())
                self.resultsSampleSelectorComboBox.clear()
                self.resultsSampleSelectorComboBox.addItems(samples)
                self.resultsSampleSelectorComboBox.setCurrentIndex(0)
            self.resultsSampleSelectorComboBox.setEnabled(True)
            self.resultsDistanceSelectorComboBox.setEnabled(True)
        except FileNotFoundError:
            return

