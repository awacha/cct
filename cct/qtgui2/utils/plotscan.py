import logging
from typing import Dict, Optional

from PyQt5 import QtWidgets, QtCore
from matplotlib.axes import Axes, np
from matplotlib.backend_bases import key_press_handler, KeyEvent
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.legend import Legend
from matplotlib.lines import Line2D
from matplotlib.text import Text

from .plotscan_ui import Ui_Form
from ..utils.window import WindowRequiresDevices
from ...core2.algorithms.peakfit import PeakType, fitpeak
from ...core2.dataclasses import Scan

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class PlotScan(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    _recording: bool = False
    figure: Figure
    canvas: FigureCanvasQTAgg
    figtoolbar: NavigationToolbar2QT
    axes: Axes
    scan: Scan = None
    lines: Dict[str, Line2D]
    legend: Optional[Legend] = None
    cursor: Optional[Line2D] = None
    peakcurve: Optional[Line2D] = None
    peakvline: Optional[Line2D] = None
    peaktext: Optional[Text] = None
    motorvline: Optional[Line2D] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figure = Figure(constrained_layout=True)
        self.axes = self.figure.add_subplot(self.figure.add_gridspec(1, 1)[:, :])
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.mpl_connect('key_press_event', self.onCanvasKeyPress)
        self.canvas.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.figtoolbar = NavigationToolbar2QT(self.canvas, self)
        self.figureVerticalLayout.addWidget(self.figtoolbar)
        self.figureVerticalLayout.addWidget(self.canvas)
        self.showAllPushButton.clicked.connect(self.showAll)
        self.hideAllPushButton.clicked.connect(self.hideAll)
        self.listWidget.itemChanged.connect(self.setPlotVisibility)
        self.showLegendToolButton.toggled.connect(self.setLegendVisibility)
        self.replotToolButton.clicked.connect(self.replot)
        self.autoScaleToolButton.clicked.connect(self.autoScaleToggled)
        self.fitAsymmetricPositiveToolButton.clicked.connect(self.fitPeak)
        self.fitSymmetricPositiveToolButton.clicked.connect(self.fitPeak)
        self.fitAsymmetricNegativeToolButton.clicked.connect(self.fitPeak)
        self.fitSymmetricNegativeToolButton.clicked.connect(self.fitPeak)
        self.motorToPeakToolButton.clicked.connect(self.motorToPeak)
        self.motorToCursorToolButton.clicked.connect(self.motorToCursor)
        self.show2DToolButton.toggled.connect(self.show2DToggled)
        self.goBackToolButton.clicked.connect(self.onSliderButton)
        self.goForwardToolButton.clicked.connect(self.onSliderButton)
        self.gotoFirstToolButton.clicked.connect(self.onSliderButton)
        self.gotoLastToolButton.clicked.connect(self.onSliderButton)
        self.listWidget.currentRowChanged.connect(self.emphasizeCurrentLine)
        self.cursorHorizontalSlider.valueChanged.connect(self.updateCursor)
        self.cursorToMaximumToolButton.clicked.connect(self.cursorToMax)
        self.cursorToMinimumToolButton.clicked.connect(self.cursorToMin)
        self.legend = None
        self.lines = {}
        self.setRecording(self._recording)
        self.canvas.setFocus(QtCore.Qt.OtherFocusReason)

    def onCanvasKeyPress(self, event: KeyEvent):
        logger.debug('Key pressed on canvas: {}'.format(event.key))
        if event.key == 'left':
            self.cursorHorizontalSlider.triggerAction(self.cursorHorizontalSlider.SliderSingleStepSub)
        elif event.key == 'right':
            self.cursorHorizontalSlider.triggerAction(self.cursorHorizontalSlider.SliderSingleStepAdd)
        elif event.key in ['shift+left', 'pagedown']:
            self.cursorHorizontalSlider.triggerAction(self.cursorHorizontalSlider.SliderPageStepSub)
        elif event.key in ['shift+right', 'pageup']:
            self.cursorHorizontalSlider.triggerAction(self.cursorHorizontalSlider.SliderPageStepAdd)
        else:
            key_press_handler(event, self.canvas, self.figtoolbar)
        return True

    def updateCursor(self):
        if self.cursor is not None:
            self.cursor.set_xdata(self.scan[self.scan.motorname][self.cursorHorizontalSlider.value()])
            self.canvas.draw_idle()
            if self.show2DToolButton.isChecked():
                self.showImage(keepzoom=True)
            self.cursorPositionLabel.setText(str(self.scan[self.scan.motorname][self.cursorHorizontalSlider.value()]))

    def showAll(self):
        self.listWidget.blockSignals(True)
        for row in range(self.listWidget.count()):
            self.listWidget.item(row).setCheckState(QtCore.Qt.Checked)
        self.listWidget.blockSignals(False)
        self.setPlotVisibility()

    def hideAll(self):
        self.listWidget.blockSignals(True)
        for row in range(self.listWidget.count()):
            self.listWidget.item(row).setCheckState(QtCore.Qt.Unchecked)
        self.listWidget.blockSignals(False)
        self.setPlotVisibility()

    def emphasizeCurrentLine(self):
        signal = self.listWidget.currentItem().text()
        for key in self.lines:
            self.lines[key].set_linewidth(3 if signal == key else 1)
        self.canvas.draw_idle()

    def onSliderButton(self):
        if self.sender() is self.goBackToolButton:
            self.cursorHorizontalSlider.triggerAction(QtWidgets.QSlider.SliderSingleStepSub)
        elif self.sender() is self.goForwardToolButton:
            self.cursorHorizontalSlider.triggerAction(QtWidgets.QSlider.SliderSingleStepAdd)
        elif self.sender() is self.gotoFirstToolButton:
            self.cursorHorizontalSlider.triggerAction(QtWidgets.QSlider.SliderToMinimum)
        else:
            assert self.sender() is self.gotoLastToolButton
            self.cursorHorizontalSlider.triggerAction(QtWidgets.QSlider.SliderToMaximum)

    def autoScaleToggled(self):
        self.axes.relim(visible_only=True)
        self.axes.autoscale(self.autoScaleToolButton.isChecked())

    def setMotorButtonsEnabled(self):
        self.motorToPeakToolButton.setEnabled(
            (self.peakposition() is not None)
            and self.instrument.online
            and (not self._recording)
            and (self.scan.motorname in self.instrument.motors)
            and (not self.instrument.motors[self.scan.motorname].isMoving()))
        self.motorToCursorToolButton.setEnabled(
            self.instrument.online
            and (not self._recording)
            and (self.scan.motorname in self.instrument.motors)
            and (not self.instrument.motors[self.scan.motorname].isMoving())
        )

    def motorToPeak(self):
        if self.peakposition() is not None:
            self.instrument.motors[self.scan.motorname].moveTo(self.peakposition())

    def motorToCursor(self):
        self.instrument.motors[self.scan.motorname].moveTo(
            self.scan[self.scan.motorname][self.cursorHorizontalSlider.value()])

    def cursorToMin(self):
        x, y = self.currentData(onlyzoomed=False)
        self.cursorHorizontalSlider.setValue(np.argmin(y))

    def cursorToMax(self):
        x, y = self.currentData(onlyzoomed=False)
        self.cursorHorizontalSlider.setValue(np.argmax(y))

    def show2DToggled(self):
        if self.show2DToolButton.isChecked():
            self.showImage(keepzoom=False)

    def showImage(self, keepzoom: bool = False):
        self.mainwindow.showPattern(
            self.instrument.io.loadExposure(
                self.instrument.config['path']['prefixes']['scn'],
                int(self.scan['FSN'][self.cursorHorizontalSlider.value()]), raw=True, check_local=True),
            keepzoom)

    def currentData(self, onlyzoomed: bool = False):
        x = self.scan[self.scan.motorname]
        y = self.scan[self.listWidget.currentItem().text()]
        if onlyzoomed:
            xmin, xmax, ymin, ymax = self.axes.axis()
            idx = np.logical_and(np.logical_and(x >= xmin, x <= xmax), np.logical_and(y >= ymin, y <= ymax))
            x = x[idx]
            y = y[idx]
        return x, y

    def fitPeak(self):
        x, y = self.currentData(onlyzoomed=True)
        symmetric = self.sender() in [self.fitSymmetricNegativeToolButton, self.fitSymmetricPositiveToolButton]
        positive = self.sender() in [self.fitSymmetricPositiveToolButton, self.fitAsymmetricPositiveToolButton]
        params, covar, fitcurvefunc = fitpeak(
            x, y if positive else -y, dx=None, dy=None,
            peaktype=PeakType.Lorentzian if symmetric else PeakType.AsymmetricLorentzian)
        xplot = np.linspace(x.min(), x.max(), 100)
        yplot = fitcurvefunc(xplot) if positive else -fitcurvefunc(xplot)
        if self.peakcurve is not None:
            self.peakcurve.remove()
        self.peakcurve = self.axes.plot(xplot, yplot, 'r-', lw=1)[0]
        if self.peaktext is not None:
            self.peaktext.remove()
        self.peaktext = self.axes.text(
            params[1], yplot.max() if positive else yplot.min(),
            f'{params[1]:g}', ha='center', va='bottom' if positive else 'top'
        )
        if self.peakvline is not None:
            self.peakvline.remove()
        self.peakvline = self.axes.axvline(params[1], lw=1, color='r', ls=':')
        self.canvas.draw_idle()
        self.setMotorButtonsEnabled()

    def peakposition(self) -> Optional[float]:
        if self.peakvline is None:
            return None
        else:
            return self.peakvline.get_xdata()[0]

    def setRecording(self, recording: bool):
        self._recording = recording
        self.cursorVerticalLayout.setEnabled(not recording)
        if self.cursor is not None:
            self.cursor.set_visible(not recording)
            if not recording:
                self.updateCursor()
        for button in [self.fitAsymmetricNegativeToolButton, self.fitAsymmetricPositiveToolButton,
                       self.fitSymmetricNegativeToolButton, self.fitSymmetricPositiveToolButton,
                       self.cursorToMaximumToolButton, self.cursorToMinimumToolButton, self.motorToCursorToolButton,
                       self.motorToPeakToolButton]:
            button.setEnabled(not recording)

    def setPlotVisibility(self):
        if not self.lines:
            return
        selected = [self.listWidget.item(row).text() for row in range(self.listWidget.count()) if
                    self.listWidget.item(row).checkState() == QtCore.Qt.Checked]
        for counter in self.lines:
            self.lines[counter].set_visible(counter in selected)
        if self.autoScaleToolButton.isChecked():
            self.axes.relim(visible_only=True)
            self.axes.autoscale_view()
        if self.legend is not None:
            self.legend.remove()
        self.legend = self.axes.legend(
            [self.lines[name] for name in self.scan.columnnames[1:] if self.lines[name].get_visible()],
            [name for name in self.scan.columnnames[1:] if self.lines[name].get_visible()]
        )
        self.legend.set_visible(self.showLegendToolButton.isChecked())
        self.canvas.draw_idle()

    def setLegendVisibility(self):
        if self.legend is not None:
            self.legend.set_visible(self.showLegendToolButton.isChecked())
            self.canvas.draw_idle()

    def replot(self):
        self.axes.clear()
        motor = self.scan.motorname
        xdata = self.scan[motor]
        self.lines = {}
        for counter in self.scan.columnnames[1:]:
            ydata = self.scan[counter]
            self.lines[counter] = self.axes.plot(xdata, ydata, '.-', label=counter, linewidth=1)[0]
        self.axes.set_xlabel(motor)
        self.axes.set_ylabel('Counters (cps)')
        self.axes.grid(True, which='both')
        self.setPlotVisibility()  # this also plots the legend
        self.emphasizeCurrentLine()
        self.cursorHorizontalSlider.setMinimum(0)
        self.cursorHorizontalSlider.setMaximum(len(self.scan)-1)
        self.cursor = self.axes.axvline(self.scan[self.scan.motorname][self.cursorHorizontalSlider.value()], lw=2,
                                        ls='dashed', color='k')
        self.cursor.set_visible(not self._recording)
        limits = self.axes.axis()
        try:
            self.motorvline = self.axes.axvline(self.instrument.motors[self.scan.motorname].where(), lw=1, ls='dotted', color='g')
            self.axes.axis(limits)
        except Exception as exc:
            logger.warning(f'Cannot plot motor vline: {exc}')
            self.motorvline = None

    def setScan(self, scan: Scan):
        if isinstance(self.scan, Scan):
            if self.instrument.online:
                self.disconnectMotor(self.instrument.motors[self.scan.motorname])
        self.scan = scan
        if self.instrument.online:
            self.connectMotor(self.instrument.motors[self.scan.motorname])
        self.listWidget.clear()
        self.listWidget.addItems(self.scan.columnnames[1:])
        for row in range(self.listWidget.count()):
            item = self.listWidget.item(row)
            item.setFlags(
                QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
        self.listWidget.setCurrentItem(self.listWidget.item(1))
        self.cursorHorizontalSlider.setMinimum(0)
        self.cursorHorizontalSlider.setMaximum(len(self.scan) - 1)
        self.cursorHorizontalSlider.setValue(len(self.scan) // 2)
        self.replot()
        self.setWindowTitle(f'Scan #{self.scan.index}: {self.scan.comment}')

    def onMotorStarted(self, startposition: float):
        self.setMotorButtonsEnabled()

    def onMotorStopped(self, success: bool, endposition: float):
        self.setMotorButtonsEnabled()

    def onMotorPositionChanged(self, newposition: float):
        if self.motorvline is not None:
            self.motorvline.set_xdata(newposition)
            self.canvas.draw_idle()
