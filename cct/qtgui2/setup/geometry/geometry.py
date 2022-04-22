import logging
from typing import Tuple, Dict, Any, Optional, Sequence

from PyQt5 import QtWidgets, QtCore, QtGui
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from .geometry_ui import Ui_Form
from .spacerselector import SpacerSelectorDialog
from ...utils.window import WindowRequiresDevices
from ...utils.filebrowsers import browseMask, getOpenFile, getSaveFile
from ....core2.instrument.components.geometry.choices import ComponentType, GeometryChoices
from ....core2.instrument.components.geometry.optimizer import GeometryOptimizer
from ....core2.instrument.components.geometry.optimizerstore import OptimizerStore


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GeometryEditor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    _optimizer: Optional[GeometryOptimizer] = None
    _optimizerstore: OptimizerStore
    _spacerselectordialog: Optional[SpacerSelectorDialog] = None
    figure: Figure
    canvas: FigureCanvasQTAgg
    figtoolbar: NavigationToolbar2QT

    _widgetname2configpath: Dict[str, Tuple[str, ...]] = {
        'l0DoubleSpinBox': ('geometry', 'sourcetoph1'),
        'lsDoubleSpinBox': ('geometry', 'ph3tosample'),
        'lbsDoubleSpinBox': ('geometry', 'beamstoptodetector'),
        'lfpDoubleSpinBox': ('geometry', 'ph3toflightpipes'),
        'lfp2detDoubleSpinBox': ('geometry', 'lastflightpipetodetector'),
        'pixelSizeValDoubleSpinBox': ('geometry', 'pixelsize'),
        'pixelSizeErrDoubleSpinBox': ('geometry', 'pixelsize.err'),
        'wavelengthValDoubleSpinBox': ('geometry', 'wavelength'),
        'wavelengthErrDoubleSpinBox': ('geometry', 'wavelength.err'),
        'sealingRingWidthDoubleSpinBox': ('geometry', 'isoKFspacer'),
        'L1WithoutSpacersDoubleSpinBox': ('geometry', 'l1base'),
        'L2WithoutSpacersDoubleSpinBox': ('geometry', 'l2base'),
        'D1DoubleSpinBox': ('geometry', 'pinhole_1'),
        'D2DoubleSpinBox': ('geometry', 'pinhole_2'),
        'D3DoubleSpinBox': ('geometry', 'pinhole_3'),
        'DBSDoubleSpinBox': ('geometry', 'beamstop'),
        'descriptionPlainTextEdit': ('geometry', 'description'),
        'sdValDoubleSpinBox': ('geometry', 'dist_sample_det'),
        'sdErrDoubleSpinBox': ('geometry', 'dist_sample_det.err'),
        'beamPosXValDoubleSpinBox': ('geometry', 'beamposx'),
        'beamPosXErrDoubleSpinBox': ('geometry', 'beamposx.err'),
        'beamPosYValDoubleSpinBox': ('geometry', 'beamposy'),
        'beamPosYErrDoubleSpinBox': ('geometry', 'beamposy.err'),
        'maskFileNameLineEdit': ('geometry', 'mask'),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._optimizerstore = OptimizerStore()
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.choicesTreeView.setModel(self.instrument.geometry.choices)
        self.addChoiceToolButton.clicked.connect(self.addChoice)
        self.removeChoiceToolButton.clicked.connect(self.removeChoice)
        self.choicesTreeView.selectionModel().currentChanged.connect(self.onChoicesTreeViewCurrentChanged)
        sortmodel = QtCore.QSortFilterProxyModel()
        sortmodel.setSourceModel(self._optimizerstore)
        sortmodel.setSortRole(QtCore.Qt.EditRole)
        self.optimizationTreeView.setModel(sortmodel)
        for name, path in self._widgetname2configpath.items():
            obj = getattr(self, name)
            assert isinstance(obj, QtWidgets.QWidget)
            try:
                value = self.instrument.config[path]
            except KeyError:
                pass
            if isinstance(obj, QtWidgets.QDoubleSpinBox):
                obj.setValue(float(value))
                obj.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
            elif isinstance(obj, QtWidgets.QLineEdit):
                obj.setText(value)
                obj.editingFinished.connect(self.onLineEditChanged)
            elif isinstance(obj, QtWidgets.QPlainTextEdit):
                obj.setPlainText(value)
                obj.textChanged.connect(self.onPlainTextEditChanged)
            else:
                assert False

        self.recalculateCollimationProperties()
        self.l1EditToolButton.clicked.connect(self.editSpacers)
        self.l2EditToolButton.clicked.connect(self.editSpacers)
        self.flightpipesToolButton.clicked.connect(self.editSpacers)
        self.optimizePushButton.clicked.connect(self.doOptimization)
        self.updateL1L2Labels()
        self.progressBar.setVisible(False)
        self.figure = Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.figtoolbar = NavigationToolbar2QT(self.canvas, self.graphTab)
        self.graphTab.setLayout(QtWidgets.QVBoxLayout())
        self.graphTab.layout().addWidget(self.canvas)
        self.graphTab.layout().addWidget(self.figtoolbar)
        self.optimizationTreeView.selectionModel().selectionChanged.connect(self.onOptimizationSelectionChanged)
        self.browseMaskPushButton.clicked.connect(self.onBrowseMask)
        self.updateSetupParametersPushButton.clicked.connect(self.updateSetupParameters)
        self.loadPresetPushButton.clicked.connect(self.onLoadPreset)
        self.savePresetPushButton.clicked.connect(self.onSavePreset)

    def onLoadPreset(self):
        filename = getOpenFile(self, 'Load geometry from a file',
                               filters='Geometry files (*.geop *.geoj);;'
                                       'Geometry pickle files (*.geop);;'
                                       'Geometry JSON files (*.geoj);;'
                                       'All files (*)')
        if not filename:
            return
        self.instrument.geometry.loadGeometry(filename)

    def onSavePreset(self):
        filename = getSaveFile(self, 'Save geometry to a file', defaultsuffix='.geo',
                               filters='Geometry files (*.geop *.geoj);;'
                                       'Geometry pickle files (*.geop);;'
                                       'Geometry JSON files (*.geoj);;'
                                       'All files (*)')
        if not filename:
            return
        self.instrument.geometry.saveGeometry(filename)

    def onBrowseMask(self):
        filename = browseMask(self)
        if not filename:
            return
        self.maskFileNameLineEdit.setText(filename)
        self.maskFileNameLineEdit.editingFinished.emit()

    def updateSetupParameters(self):
        current = self.optimizationTreeView.currentIndex().row()
        dic = self._optimizerstore[current]
        self.instrument.geometry.updateFromOptimizerResult(dic)

    def onOptimizationSelectionChanged(self, selected: Sequence[QtCore.QModelIndex],
                                       deselected: Sequence[QtCore.QModelIndex]):
        self.updateSetupParametersPushButton.setEnabled(
            bool(len(self.optimizationTreeView.selectionModel().selectedRows(0))))
        self.copyToClipboardPushButton.setEnabled(bool(len(self.optimizationTreeView.selectionModel().selectedRows(0))))

    def doOptimization(self):
        if self._optimizer is not None:
            self._optimizer.stopevent.set()
#            QtWidgets.QMessageBox.critical(self, 'Cannot start optimization', 'Optimization process already running')
            return
        self._optimizer = GeometryOptimizer(self.instrument.config)
        self._optimizer.finished.connect(self.onOptimizationFinished)
        self._optimizer.geometryFound.connect(self.onOptimizationGeometryFound)
        logger.info('Starting geometry search')
        self._optimizerstore.clear()
        self._optimizer.start(
            (self.minMaxSampleSizeDoubleSpinBox.value(), self.maxMaxSampleSizeDoubleSpinBox.value()),
            (self.optQMinMinDoubleSpinBox.value(), self.optQMinMaxDoubleSpinBox.value()),
            self.minPh1Ph2DistanceDoubleSpinBox.value(), self.minPh2Ph3DistanceDoubleSpinBox.value(),
            self.maxCameraLengthDoubleSpinBox.value())
        self.progressBar.setVisible(True)
        self.optimizePushButton.setText('Stop')
        self.optimizePushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/stop.svg")))

    def onOptimizationGeometryFound(self, optresult: Dict[str, Any]):
        self._optimizerstore.addOptResult(optresult)

    def onOptimizationFinished(self, elapsedtime: float):
        self._optimizer.deleteLater()
        del self._optimizer
        self._optimizer = None
        logger.info('Geometry search finished.')
        self.progressBar.setVisible(False)
        QtWidgets.QMessageBox.information(
            self, 'Geometry search finished',
            f'Searching for geometries finished in {elapsedtime // 60:.0f} minutes {elapsedtime % 60:.2f} seconds, '
            f'found {self._optimizerstore.rowCount()} compatible geometries.'
        )
        logger.debug('Plotting...')
        self.figure.clear()
        axes = self.figure.add_subplot(1, 1, 1)
        qmin = [p["qmin"] for p in self._optimizerstore]
        intensity = [p["intensity"] for p in self._optimizerstore]
        axes.plot(qmin, intensity, '.')
        axes.set_xlabel('Lowest q (nm$^{-1}$)')
        axes.set_ylabel('Intensity (\u03bcm$^4$ mm$^{-2}$)')
        axes.grid(True, which='both')
        logger.debug('Redrawing...')
        self.canvas.draw_idle()
        self.optimizePushButton.setText('Find optimum')
        self.optimizePushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/start.svg")))

    @staticmethod
    def setLabelBackground(label: QtWidgets.QLabel, good: bool):
        pal = label.palette()
        pal.setColor(pal.Window, QtGui.QColor('red' if not good else 'lightgreen'))
        label.setPalette(pal)
        label.setAutoFillBackground(True)

    def recalculateCollimationProperties(self):
        self.relativeintensityLabel.setText(f'{self.instrument.config["geometry"]["intensity"]:.4f}')
        self.qMinLabel.setText(f'{self.instrument.config["geometry"]["qmin"]:.4f}')
        self.maxRgLabel.setText(f'{1/self.instrument.config["geometry"]["qmin"]:.4f}')
        parasiticscattering_around_bs = self.instrument.config["geometry"]["dparasitic_at_bs"] > self.instrument.config["geometry"]["beamstop"]
        self.parasiticScatteringLabel.setText(
            'Expected' if parasiticscattering_around_bs else 'Not Expected')
        self.setLabelBackground(self.parasiticScatteringLabel, not parasiticscattering_around_bs)
        directbeam_around_bs = self.instrument.config['geometry']['dbeam_at_bs'] > self.instrument.config['geometry']['beamstop']
        self.directBeamHitsDetectorLabel.setText(
            'YES!!!' if directbeam_around_bs else 'No')
        self.setLabelBackground(self.directBeamHitsDetectorLabel, not directbeam_around_bs)
        self.sampleSizeLabel.setText(f'{self.instrument.config["geometry"]["dbeam_at_sample"]:.2f}')
        self.beamStopSizeLabel.setText(f'{self.instrument.config["geometry"]["dbeam_at_bs"]:.2f}')
        ph3_cuts_beam = self.instrument.config["geometry"]["dbeam_at_ph3"] > self.instrument.config["geometry"]["pinhole_3"]/1000.0
        self.pinhole3LargeEnoughLabel.setText(
            'NO!!!' if ph3_cuts_beam else 'Yes')
        self.setLabelBackground(self.pinhole3LargeEnoughLabel, not ph3_cuts_beam)

    def updateL1L2Labels(self):
        self.l1Label.setText(f'{self.instrument.geometry.l1():.2f}')
        self.l2Label.setText(f'{self.instrument.geometry.l2():.2f}')
        self.flightpipesLabel.setText(
            ' + '.join([f'{x:.0f} mm' for x in self.instrument.config['geometry']['flightpipes']]))
        self.l1Label.setToolTip(' + '.join([f'{x:.0f} mm' for x in self.instrument.config['geometry']['l1_elements']]))
        self.l2Label.setToolTip(' + '.join([f'{x:.0f} mm' for x in self.instrument.config['geometry']['l2_elements']]))

    def editSpacers(self):
        assert self.sender() in [self.l1EditToolButton, self.l2EditToolButton, self.flightpipesToolButton]
        if self._spacerselectordialog is not None:
            raise RuntimeError('Spacer / flight pipe selector dialog is already running.')
        allspacers = list(
            self.instrument.geometry.choices.flightpipes) if self.sender() is self.flightpipesToolButton else list(
            self.instrument.geometry.choices.spacers)
        if self.sender() in [self.l1EditToolButton, self.l2EditToolButton]:
            this = self.instrument.geometry.currentpreset.l2_elements if self.sender() == self.l2EditToolButton else self.instrument.geometry.currentpreset.l1_elements
            other = self.instrument.geometry.currentpreset.l1_elements if self.sender() == self.l2EditToolButton else self.instrument.geometry.currentpreset.l2_elements
            for spacer in other:
                allspacers.remove(spacer)
            target = SpacerSelectorDialog.TargetTypes.L1 if self.sender() == self.l1EditToolButton else SpacerSelectorDialog.TargetTypes.L2
        elif self.sender() == self.flightpipesToolButton:
            this = self.instrument.geometry.currentpreset.flightpipes
            target = SpacerSelectorDialog.TargetTypes.FlightPipes
        else:
            assert False
        self._spacerselectordialog = SpacerSelectorDialog(self, allspacers, this, target)
        self._spacerselectordialog.finished.connect(self.spacerSelectorFinished)
        self._spacerselectordialog.open()

    def spacerSelectorFinished(self, result: int):
        if result == QtWidgets.QDialog.Accepted:
            if self._spacerselectordialog.target == SpacerSelectorDialog.TargetTypes.L2:
                self.instrument.geometry.currentpreset.l2_elements = self._spacerselectordialog.selectedSpacers()
            elif self._spacerselectordialog.target == SpacerSelectorDialog.TargetTypes.L1:
                self.instrument.geometry.currentpreset.l1_elements = self._spacerselectordialog.selectedSpacers()
            elif self._spacerselectordialog.target == SpacerSelectorDialog.TargetTypes.FlightPipes:
                self.instrument.geometry.currentpreset.flightpipes = self._spacerselectordialog.selectedSpacers()
            else:
                assert False
        self._spacerselectordialog.close()
        self._spacerselectordialog.deleteLater()
        del self._spacerselectordialog
        self.updateL1L2Labels()

    def onDoubleSpinBoxValueChanged(self, newvalue: float):
        w = self.sender()
        path = [p for wn, p in self._widgetname2configpath.items() if wn == w.objectName()][0]
        assert isinstance(path, tuple)
        assert all([isinstance(k, str) for k in path])
        self.instrument.config[path] = newvalue

    def onLineEditChanged(self):
        w = self.sender()
        path = [p for wn, p in self._widgetname2configpath.items() if wn == w.objectName()][0]
        assert isinstance(path, tuple)
        assert all([isinstance(k, str) for k in path])
        self.instrument.config[path] = w.text()

    def onPlainTextEditChanged(self):
        w = self.sender()
        path = [p for wn, p in self._widgetname2configpath.items() if wn == w.objectName()][0]
        assert isinstance(path, tuple)
        assert all([isinstance(k, str) for k in path])
        self.instrument.config[path] = w.toPlainText()

    def onChoicesTreeViewCurrentChanged(self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex):
        if not current.isValid():
            logger.debug('Current index is not valid')
        else:
            logger.debug(f'Current index data: {current.internalPointer()}')

    def addChoice(self):
        current = self.choicesTreeView.selectionModel().currentIndex()
        if not current.isValid():
            return
        ip = current.internalPointer()
        logger.debug(ip)
        assert isinstance(ip, GeometryChoices.IndexObject)
        if ip.componenttype == ComponentType.Beamstop:
            self.instrument.geometry.choices.addBeamstop(0.0)
        elif ip.componenttype == ComponentType.FlightPipe:
            self.instrument.geometry.choices.addFlightPipe(0.0)
        elif ip.componenttype == ComponentType.PinholeSpacer:
            self.instrument.geometry.choices.addSpacer(0.0)
        elif (ip.componenttype == ComponentType.Pinhole) and (ip.level == 2):
            self.instrument.geometry.choices.addPinhole(ip.index1, 0.0)
        else:
            return

    def removeChoice(self):
        current = self.choicesTreeView.selectionModel().currentIndex()
        if not current.isValid():
            return
        ip = current.internalPointer()
        assert isinstance(ip, GeometryChoices.IndexObject)
        if (((ip.componenttype == ComponentType.Beamstop) and (ip.level == 2)) or
                ((ip.componenttype == ComponentType.FlightPipe) and (ip.level == 2)) or
                ((ip.componenttype == ComponentType.PinholeSpacer) and (ip.level == 2)) or
                ((ip.componenttype == ComponentType.Pinhole) and (ip.level == 3))):
            self.instrument.geometry.choices.removeRow(current.row(), current.parent())

    def onConfigChanged(self, path: Tuple[str, ...], newvalue: Any):
        if path[0] != 'geometry':
            return
        elif path in [('geometry', 'l1_elements'), ('geometry', 'l2_elements'), ('geometry', 'flightpipes')]:
            self.updateL1L2Labels()
        else:
            try:
                widgetname = [wn for wn, p in self._widgetname2configpath.items() if p == path][0]
            except IndexError:
                return
            widget = getattr(self, widgetname)
            widget.blockSignals(True)
            try:
                if isinstance(widget, QtWidgets.QDoubleSpinBox):
                    widget.setValue(newvalue)
                elif isinstance(widget, QtWidgets.QPlainTextEdit):
                    widget.setPlainText(newvalue)
                elif isinstance(widget, QtWidgets.QLineEdit):
                    widget.setText(newvalue)
                else:
                    assert False
            finally:
                widget.blockSignals(False)
        self.recalculateCollimationProperties()
