import logging
from typing import Tuple, Dict, Any, Optional, Sequence

from PyQt5 import QtWidgets, QtCore, QtGui
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from .geometry_ui import Ui_Form
from .spacerselector import SpacerSelectorDialog
from ...utils.window import WindowRequiresDevices
from ....core2.instrument.components.geometry.choices import ComponentType, GeometryChoices
from ....core2.instrument.components.geometry.optimizer import GeometryOptimizer, GeometryPreset
from ....core2.instrument.components.geometry.presetstore import PresetStore

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GeometryEditor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    _optimizer: Optional[GeometryOptimizer] = None
    _optpresets: PresetStore
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
    }

    _geometryproperty2widgetname: Dict[str, Tuple[str, ...]] = {
        #        'l1_elements': (None,),  # these are handled separately
        #        'l2_elements': (None,),  # these are handled separately
        'pinhole1': ('D1DoubleSpinBox',),
        'pinhole2': ('D2DoubleSpinBox',),
        'pinhole3': ('D3DoubleSpinBox',),
        'beamstop': ('DBSDoubleSpinBox',),
        'description': ('descriptionPlainTextEdit',),
        'sd': ('sdValDoubleSpinBox', 'sdErrDoubleSpinBox'),
        'beamposx': ('beamPosXValDoubleSpinBox', 'beamPosXErrDoubleSpinBox'),
        'beamposy': ('beamPosYValDoubleSpinBox', 'beamPosYErrDoubleSpinBox'),
        'mask': ('maskFileNameLineEdit',),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self._optpresets = PresetStore()
        self.choicesTreeView.setModel(self.instrument.geometry.choices)
        self.addChoiceToolButton.clicked.connect(self.addChoice)
        self.removeChoiceToolButton.clicked.connect(self.removeChoice)
        self.choicesTreeView.selectionModel().currentChanged.connect(self.onChoicesTreeViewCurrentChanged)
        self.optimizationTreeView.setModel(self._optpresets)
        self.presetsListView.setModel(self.instrument.geometry)
        for name, path in self._widgetname2configpath.items():
            obj = getattr(self, name)
            assert isinstance(obj, QtWidgets.QDoubleSpinBox)
            try:
                obj.setValue(float(self.instrument.config[path]))
            except KeyError:
                pass
            obj.valueChanged.connect(self.onDoubleSpinBoxValueChanged)
        for propertyname, widgetnames in self._geometryproperty2widgetname.items():
            widgets = [getattr(self, wn) for wn in widgetnames]
            if len(widgets) == 1 and isinstance(widgets[0], QtWidgets.QDoubleSpinBox):
                widgets[0].setValue(getattr(self.instrument.geometry.currentpreset, propertyname))
                widgets[0].valueChanged.connect(self.onGeometryParameterChangedInUI)
            elif len(widgets) == 1 and isinstance(widgets[0], QtWidgets.QLineEdit):
                widgets[0].setText(getattr(self.instrument.geometry.currentpreset, propertyname))
                widgets[0].editingFinished.connect(self.onGeometryParameterChangedInUI)
            elif len(widgets) == 1 and isinstance(widgets[0], QtWidgets.QPlainTextEdit):
                widgets[0].setPlainText(getattr(self.instrument.geometry.currentpreset, propertyname))
                widgets[0].textChanged.connect(self.onGeometryParameterChangedInUI)
            elif len(widgets) == 2 and isinstance(widgets[0], QtWidgets.QDoubleSpinBox) and isinstance(widgets[1],
                                                                                                       QtWidgets.QDoubleSpinBox):
                value = getattr(self.instrument.geometry.currentpreset, propertyname)
                assert isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], float) and isinstance(
                    value[1], float)
                widgets[0].setValue(value[0])
                widgets[1].setValue(value[1])
                widgets[0].valueChanged.connect(self.onGeometryParameterChangedInUI)
                widgets[1].valueChanged.connect(self.onGeometryParameterChangedInUI)
            else:
                assert False
        self.recalculateCollimationProperties()
        self.l1EditToolButton.clicked.connect(self.editSpacers)
        self.l2EditToolButton.clicked.connect(self.editSpacers)
        self.flightpipesToolButton.clicked.connect(self.editSpacers)
        self.addPresetToolButton.clicked.connect(self.addPreset)
        self.savePresetToolButton.clicked.connect(self.savePreset)
        self.removePresetToolButton.clicked.connect(self.removePreset)
        self.loadPresetToolButton.clicked.connect(self.loadPreset)
        self.loadPresetToolButton.setEnabled(False)
        self.removePresetToolButton.setEnabled(False)
        self.savePresetToolButton.setEnabled(False)
        self.presetsListView.selectionModel().currentChanged.connect(self.currentSelectedPresetChanged)
        self.instrument.geometry.currentPresetChanged.connect(self.onGeometryChanged)
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
        self.updateSetupParametersPushButton.clicked.connect(self.updateSetupParameters)

    def updateSetupParameters(self):
        current = self.optimizationTreeView.currentIndex().row()
        self.instrument.geometry.setCurrentPreset(self._optpresets[current])

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
        self._optpresets.clear()
        self._optimizer.start(
            self.maxSampleSizeDoubleSpinBox.value(), self.optQMinDoubleSpinBox.value(),
            self.minPh1Ph2DistanceDoubleSpinBox.value(), self.minPh2Ph3DistanceDoubleSpinBox.value(),
            self.maxCameraLengthDoubleSpinBox.value())
        self.progressBar.setVisible(True)
        self.optimizePushButton.setText('Stop')
        self.optimizePushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/stop.svg")))

    def onOptimizationGeometryFound(self, preset: GeometryPreset):
        self._optpresets.addPreset(preset)

    def onOptimizationFinished(self, elapsedtime: float):
        self._optimizer.deleteLater()
        del self._optimizer
        self._optimizer = None
        logger.info('Geometry search finished.')
        self.progressBar.setVisible(False)
        QtWidgets.QMessageBox.information(
            self, 'Geometry search finished',
            f'Searching for geometries finished in {elapsedtime // 60:.0f} minutes {elapsedtime % 60:.2f} seconds, '
            f'found {self._optpresets.rowCount()} compatible geometries.'
        )
        logger.debug('Sorting...')
        self._optpresets.sort(self.optimizationTreeView.header().sortIndicatorSection(), self.optimizationTreeView.header().sortIndicatorOrder())
        logger.debug('Plotting...')
        self.figure.clear()
        axes = self.figure.add_subplot(1, 1, 1)
        qmin = [p.qmin for p in self._optpresets]
        intensity = [p.intensity for p in self._optpresets]
        axes.plot(qmin, intensity, '.')
        axes.set_xlabel('Lowest q (nm$^{-1}$)')
        axes.set_ylabel('Intensity (\u03bcm$^4$ mm$^{-2}$)')
        axes.grid(True, which='both')
        logger.debug('Redrawing...')
        self.canvas.draw_idle()
        self.optimizePushButton.setText('Find optimum')
        self.optimizePushButton.setIcon(QtGui.QIcon(QtGui.QPixmap(":/icons/start.svg")))

    def onGeometryChanged(self, propertyname: Optional[str] = None, value: Any = None):
        logger.debug(f'Geometry changed. {propertyname=}, {value=}')
        if propertyname in ['l1_elements', 'l2_elements', 'flightpipes']:
            self.updateL1L2Labels()
        elif propertyname is not None:
            widgetnames = [wns for pn, wns in self._geometryproperty2widgetname.items() if pn == propertyname][0]
            widgets = [getattr(self, wn) for wn in widgetnames]
            for w in widgets:
                assert isinstance(w, QtWidgets.QWidget)
                w.blockSignals(True)
            try:
                if (len(widgets) == 2) and isinstance(widgets[0], QtWidgets.QDoubleSpinBox) and isinstance(widgets[1],
                                                                                                           QtWidgets.QDoubleSpinBox):
                    assert isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], float) and isinstance(
                        value[1], float)
                    widgets[0].setValue(value[0])
                    widgets[1].setValue(value[1])
                elif len(widgets) == 1:
                    widget = widgets[0]
                    if isinstance(widget, QtWidgets.QDoubleSpinBox):
                        assert isinstance(value, float)
                        widget.setValue(value)
                    elif isinstance(widget, QtWidgets.QPlainTextEdit):
                        assert isinstance(value, str)
                        widget.setPlainText(value)
                    elif isinstance(widget, QtWidgets.QLineEdit):
                        assert isinstance(value, str)
                        widget.setText(value)
                    else:
                        assert False
            finally:
                for w in widgets:
                    w.blockSignals(False)
        self.recalculateCollimationProperties()

    @staticmethod
    def setLabelBackground(label: QtWidgets.QLabel, good: bool):
        pal = label.palette()
        pal.setColor(pal.Window, QtGui.QColor('red' if not good else 'lightgreen'))
        label.setPalette(pal)
        label.setAutoFillBackground(True)

    def recalculateCollimationProperties(self):
        self.relativeintensityLabel.setText(f'{self.instrument.geometry.currentpreset.intensity:.4f}')
        self.qMinLabel.setText(f'{self.instrument.geometry.currentpreset.qmin:.4f}')
        self.maxRgLabel.setText(f'{self.instrument.geometry.currentpreset.Rgmax:.4f}')
        self.parasiticScatteringLabel.setText(
            'Not expected' if self.instrument.geometry.currentpreset.is_beamstop_large_enough_parasitic else 'Expected')
        self.setLabelBackground(self.parasiticScatteringLabel, self.instrument.geometry.currentpreset.is_beamstop_large_enough_parasitic)
        self.directBeamHitsDetectorLabel.setText(
            'No' if self.instrument.geometry.currentpreset.is_beamstop_large_enough_direct else 'YES!!!')
        self.setLabelBackground(self.directBeamHitsDetectorLabel, self.instrument.geometry.currentpreset.is_beamstop_large_enough_direct)
        self.sampleSizeLabel.setText(f'{self.instrument.geometry.currentpreset.dsample:.2f}')
        self.beamStopSizeLabel.setText(f'{self.instrument.geometry.currentpreset.dbeamstop:.2f}')
        self.pinhole3LargeEnoughLabel.setText(
            'Yes' if self.instrument.geometry.currentpreset.is_pinhole3_large_enough else 'NO!!!')
        self.setLabelBackground(self.pinhole3LargeEnoughLabel, self.instrument.geometry.currentpreset.is_pinhole3_large_enough)

    def onGeometryParameterChangedInUI(self):
        widget = self.sender()
        propertyname = [pn for pn, wns in self._geometryproperty2widgetname.items() if widget.objectName() in wns][0]
        if isinstance(widget, QtWidgets.QDoubleSpinBox):
            prevvalue = getattr(self.instrument.geometry.currentpreset, propertyname)
            if len(self._geometryproperty2widgetname[propertyname]) == 2:
                if widget.objectName().endswith('ValDoubleSpinBox'):
                    newvalue = (widget.value(), prevvalue[1])
                elif widget.objectName().endswith('ErrDoubleSpinBox'):
                    newvalue = (prevvalue[0], widget.value())
                else:
                    assert False
            else:
                newvalue = widget.value()
            setattr(self.instrument.geometry.currentpreset, propertyname, newvalue)
        elif isinstance(widget, QtWidgets.QPlainTextEdit):
            setattr(self.instrument.geometry.currentpreset, propertyname, widget.toPlainText())
        elif isinstance(widget, QtWidgets.QLineEdit):
            setattr(self.instrument.geometry.currentpreset, propertyname, widget.text())
        else:
            assert False

    def currentSelectedPresetChanged(self, selected: QtCore.QModelIndex, previous: QtCore.QModelIndex):
        self.savePresetToolButton.setEnabled(selected.isValid())
        self.loadPresetToolButton.setEnabled(selected.isValid())
        self.removePresetToolButton.setEnabled(selected.isValid())

    def addPreset(self):
        self.instrument.geometry.addPreset('Untitled')

    def removePreset(self):
        self.instrument.geometry.removePreset(self.presetsListView.currentIndex().data(QtCore.Qt.DisplayRole))

    def savePreset(self):
        self.instrument.geometry.savePreset(self.presetsListView.currentIndex().data(QtCore.Qt.DisplayRole))

    def loadPreset(self):
        self.instrument.geometry.loadPreset(self.presetsListView.currentIndex().data(QtCore.Qt.DisplayRole))

    def updateL1L2Labels(self):
        self.l1Label.setText(f'{self.instrument.geometry.currentpreset.l1:.2f}')
        self.l2Label.setText(f'{self.instrument.geometry.currentpreset.l2:.2f}')
        self.flightpipesLabel.setText(
            ' + '.join([f'{x:.0f} mm' for x in self.instrument.geometry.currentpreset.flightpipes]))
        self.l1Label.setToolTip(' + '.join([f'{x:.0f} mm' for x in self.instrument.geometry.currentpreset.l1_elements]))
        self.l2Label.setToolTip(' + '.join([f'{x:.0f} mm' for x in self.instrument.geometry.currentpreset.l2_elements]))

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
        try:
            widgetname = [wn for wn, p in self._widgetname2configpath.items() if p == path][0]
        except IndexError:
            return
        widget = getattr(self, widgetname)
        assert isinstance(widget, QtWidgets.QDoubleSpinBox)
        widget.blockSignals(True)
        try:
            widget.setValue(newvalue)
        finally:
            widget.blockSignals(False)
        self.recalculateCollimationProperties()
