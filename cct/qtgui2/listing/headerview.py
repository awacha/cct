import logging
import multiprocessing
import queue
from typing import Optional

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Slot

from .headerview_ui import Ui_Form
from ..utils.window import WindowRequiresDevices
from ...core2.dataclasses import Header, Exposure
from ...core2.instrument.components.datareduction import DataReductionPipeLine
from ...core2.views.headerviewmodel import HeaderViewModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HeaderView(WindowRequiresDevices, QtWidgets.QWidget, Ui_Form):
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
        lastfsn = self.instrument.io.lastfsn(self.instrument.config['path']['prefixes']['crd'])
        if lastfsn is None:
            self.firstFSNSpinBox.setEnabled(False)
            self.lastFSNSpinBox.setEnabled(False)
        else:
            self.firstFSNSpinBox.setRange(0, lastfsn)
            self.lastFSNSpinBox.setRange(0, lastfsn)
        self.instrument.io.lastFSNChanged.connect(self.onLastFSNChanged)
        self.reloadToolButton.clicked.connect(self.reload)
        self.showImageToolButton.clicked.connect(self.showImage)
        self.showCurveToolButton.clicked.connect(self.showCurve)
        self.stopPushButton.clicked.connect(self.onStop)
        self.dataReductionToolButton.clicked.connect(self.dataReduction)
        self.progressBar.hide()
        self.stopPushButton.hide()

    @Slot(bool)
    def onHeadersLoading(self, loading: bool):
        self.progressBar.setVisible(loading)
        self.stopPushButton.setVisible(loading)
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

    @Slot(str, int)
    def onLastFSNChanged(self, prefix: str, lastfsn: Optional[int]):
        if prefix == self.instrument.config['path']['prefixes']['crd']:
            if lastfsn is None:
                self.firstFSNSpinBox.setEnabled(False)
                self.lastFSNSpinBox.setEnabled(False)
            else:
                self.firstFSNSpinBox.setEnabled(True)
                self.lastFSNSpinBox.setEnabled(True)
                self.firstFSNSpinBox.setMaximum(lastfsn)
                self.lastFSNSpinBox.setMaximum(lastfsn)

    @Slot()
    def onStop(self):
        if self.model.isLoading():
            self.model.stopLoading()
        elif self.datareductionpipeline is not None:
            self.stopprocessingevent.set()

    @Slot()
    def reload(self):
        if self.firstFSNSpinBox.isEnabled() and self.lastFSNSpinBox.isEnabled():
            self.model.reload(range(self.firstFSNSpinBox.value(), self.lastFSNSpinBox.value() + 1))

    @Slot()
    def showImage(self):
        if self.headersTreeView.selectionModel().currentIndex().isValid():
            header = self.headersTreeView.selectionModel().currentIndex().data(QtCore.Qt.ItemDataRole.UserRole)
            assert isinstance(header, Header)
            exposure = self.instrument.io.loadExposure(
                self.instrument.config['path']['prefixes']['crd'], header.fsn, raw=True, check_local=True)
            self.mainwindow.showPattern(exposure)

    @Slot()
    def showCurve(self):
        if self.headersTreeView.selectionModel().currentIndex().isValid():
            header = self.headersTreeView.selectionModel().currentIndex().data(QtCore.Qt.ItemDataRole.UserRole)
            assert isinstance(header, Header)
            exposure = self.instrument.io.loadExposure(
                self.instrument.config['path']['prefixes']['crd'], header.fsn, raw=True, check_local=True)
            self.mainwindow.showCurve(exposure)

    @Slot()
    def dataReduction(self):
        if self.datareductionpipeline is not None:
            QtWidgets.QMessageBox.critical(self, 'Error', 'Data reduction already running')
            return
        if not len(self.headersTreeView.selectionModel().selectedRows(0)):
            return
        logger.debug('Starting a new data reduction pipeline')
        self.queuetodatareduction = multiprocessing.Queue()
        self.queuefromdatareduction = multiprocessing.Queue()
        logger.debug('Got queues')
        self.stopprocessingevent = multiprocessing.Event()
        logger.debug('Got event')
        self.datareductionpipeline = multiprocessing.Process(
            target=DataReductionPipeLine.run_in_background,
            args=(self.instrument.config.asdict(), self.queuetodatareduction, self.queuefromdatareduction,
                  self.stopprocessingevent))
        logger.debug('Starting process')
        self.datareductionpipeline.start()
        logger.debug('Starting timer')
        self.startTimer(100, QtCore.Qt.TimerType.VeryCoarseTimer)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(len(self.headersTreeView.selectionModel().selectedRows(0)))
        self.progressBar.setValue(0)
        self.progressBar.setFormat('Starting data reduction...')
        self.progressBar.show()
        self.stopPushButton.show()
        logger.debug('Queuing jobs')
        for index in self.headersTreeView.selectionModel().selectedRows(0):
            header = index.data(QtCore.Qt.ItemDataRole.UserRole)
            logger.debug(f'Queueing job with fsn {header.fsn}')
            self.queuetodatareduction.put(('process', (self.instrument.config['path']['prefixes']['crd'], header.fsn)))
        self.queuetodatareduction.put(('end', None))
        self.headersTreeView.setEnabled(False)
        logger.info('All set up.')

    def timerEvent(self, timerevent: QtCore.QTimerEvent) -> None:
        try:
            cmd, arg = self.queuefromdatareduction.get_nowait()
        except queue.Empty:
            return
#        logger.debug(f'Reply from the dara reduction pipeline: {cmd=}, {arg=}')
        if cmd == 'finished':
            self.killTimer(timerevent.timerId())
            self.progressBar.hide()
            self.stopPushButton.hide()
            self.headersTreeView.setEnabled(True)
            logger.debug('Joining data reduction pipeline')
            self.datareductionpipeline.join()
            logger.debug('Joined data reduction pipeline')
            self.datareductionpipeline.close()
            # self.queuefromdatareduction.join()
            # self.queuetodatareduction.join()
            self.datareductionpipeline = self.queuetodatareduction = self.queuefromdatareduction = \
                self.stopprocessingevent = None
        elif cmd == 'result':
            assert isinstance(arg, Exposure)
            # not ready: set visibility etc.
            self.progressBar.setValue(self.progressBar.value() + 1)
            self.progressBar.setFormat(f'Processed {self.progressBar.value()}/{self.progressBar.maximum()}')
        elif cmd == 'log':
            loglevel, message = arg
            logger.log(loglevel, message)
        else:
            assert False
