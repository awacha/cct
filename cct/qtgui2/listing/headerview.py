from typing import Optional

from PyQt5 import QtWidgets, QtCore
from .headerview_ui import Ui_Form
from ..utils.window import WindowRequiresDevices
from .headerviewmodel import HeaderViewModel
from ...core2.dataclasses import Header, Exposure
from ...core2.instrument.components.datareduction import DataReductionPipeLine
import multiprocessing
import queue
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class HeaderView(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    model: HeaderViewModel
    datareductionpipeline: Optional[multiprocessing.Process] = None
    queuetodatareduction: Optional[multiprocessing.Queue] = None
    queuefromdatareduction: Optional[multiprocessing.Queue] = None
    stopprocessingevent: Optional[multiprocessing.Event] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.model = HeaderViewModel()
        self.model.loading.connect(self.onHeadersLoading)
        self.headersTreeView.setModel(self.model)
        self.firstFSNSpinBox.setMinimum(0)
        self.firstFSNSpinBox.setMaximum(self.instrument.io.lastfsn(self.instrument.config['path']['prefixes']['crd']))
        self.lastFSNSpinBox.setMinimum(0)
        self.lastFSNSpinBox.setMaximum(self.instrument.io.lastfsn(self.instrument.config['path']['prefixes']['crd']))
        self.instrument.io.lastFSNChanged.connect(self.onLastFSNChanged)
        self.reloadToolButton.clicked.connect(self.reload)
        self.showImageToolButton.clicked.connect(self.showImage)
        self.showCurveToolButton.clicked.connect(self.showCurve)
        self.dataReductionToolButton.clicked.connect(self.dataReduction)
        self.progressBar.hide()

    def onHeadersLoading(self, loading: bool):
        self.progressBar.setVisible(loading)
        self.headersTreeView.setEnabled(not loading)
        self.dataReductionToolButton.setEnabled(not loading)
        self.firstFSNSpinBox.setEnabled(not loading)
        self.lastFSNSpinBox.setEnabled(not loading)
        self.reloadToolButton.setEnabled(not loading)
        self.showCurveToolButton.setEnabled(not loading)
        self.showImageToolButton.setEnabled(not loading)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)
        self.progressBar.setFormat('Loading headers...')

    def onLastFSNChanged(self, prefix: str, lastfsn: int):
        if prefix == self.instrument.config['path']['prefixes']['crd']:
            self.firstFSNSpinBox.setMaximum(lastfsn)
            self.lastFSNSpinBox.setMaximum(lastfsn)

    def reload(self):
        self.model.reload(self.firstFSNSpinBox.value(), self.lastFSNSpinBox.value())

    def showImage(self):
        if self.headersTreeView.selectionModel().currentIndex().isValid():
            header = self.headersTreeView.selectionModel().currentIndex().data(QtCore.Qt.UserRole)
            assert isinstance(header, Header)
            exposure = self.instrument.io.loadExposure(
                self.instrument.config['path']['prefixes']['crd'], header.fsn, raw=True, check_local=True)
            self.mainwindow.plotimage.setExposure(exposure)

    def showCurve(self):
        pass

    def dataReduction(self):
        if self.datareductionpipeline is not None:
            QtWidgets.QMessageBox.critical(self, 'Error', 'Data reduction already running')
        if not len(self.headersTreeView.selectionModel().selectedRows(0)):
            return
        self.queuetodatareduction = multiprocessing.Queue()
        self.queuefromdatareduction = multiprocessing.Queue()
        self.datareductionpipeline = multiprocessing.Process(
            target = DataReductionPipeLine.run_in_background,
            args=(self.instrument.config, self.queuetodatareduction, self.queuefromdatareduction))
        self.datareductionpipeline.start()
        self.startTimer(100, QtCore.Qt.VeryCoarseTimer)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(len(self.headersTreeView.selectionModel().selectedRows(0)))
        self.progressBar.setValue(0)
        self.progressBar.show()
        for index in self.headersTreeView.selectionModel().selectedRows(0):
            header = index.data(QtCore.Qt.UserRole)
            logger.debug(f'Queueing job with fsn {header.fsn}')
            self.queuetodatareduction.put(('process', (self.instrument.config['path']['prefixes']['crd'], header.fsn)))
        self.queuetodatareduction.put(('end', None))
        self.headersTreeView.setEnabled(False)

    def timerEvent(self, timerevent: QtCore.QTimerEvent) -> None:
        try:
            cmd, arg = self.queuefromdatareduction.get_nowait()
        except queue.Empty:
            return
        logger.debug(f'Reply from the dara reduction pipeline: {cmd=}, {arg=}')
        if cmd == 'finished':
            self.killTimer(timerevent.timerId())
            self.progressBar.hide()
            self.headersTreeView.setEnabled(True)
            self.datareductionpipeline.join()
            self.queuefromdatareduction.join()
            self.queuetodatareduction.join()
            self.datareductionpipeline = self.queuetodatareduction = self.queuefromdatareduction = None
        elif cmd == 'result':
            assert isinstance(arg, Exposure)
            # not ready: set visibility etc.
            self.progressBar.setValue(self.progressBar.value()+1)
        elif cmd == 'log':
            loglevel, message = arg
            logger.log(loglevel, message)
        else:
            assert False

