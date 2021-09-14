import logging
import time
from typing import Optional, Final, Any

import numpy as np
from PyQt5 import QtWidgets, QtGui, QtCore
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure

from .monitor_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ....core2.devices.xraysource import GeniX
from ....core2.devices.device.frontend import DeviceFrontend
from ....core2.dataclasses import Exposure
from ....core2.algorithms.beamweighting import beamweights

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class MonitorMeasurement(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicetypes = ['source', 'detector']
    figureIntensity: Figure
    figurePosition: Figure
    canvasIntensity: FigureCanvasQTAgg
    canvasPosition: FigureCanvasQTAgg
    toolbarIntensity: NavigationToolbar2QT
    toolbarPosition: NavigationToolbar2QT
    axesIntensity: Axes
    axesPosition: Axes
    axesHPositionKDE: Axes
    axesVPositionKDE: Axes
    buffer: Optional[np.ndarray] = None
    cursor: Optional[int] = None  # point in the buffer where the next measurement will be written
    bufferdtype: Final[np.dtype] = np.dtype([('time', 'f4'), ('intensity', 'f4'), ('beamx', 'f4'), ('beamy', 'f4'), ])
    kdepointcount: Final[int] = 1000
    debugmode: bool=False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.figureIntensity = Figure(constrained_layout=True)
        self.canvasIntensity = FigureCanvasQTAgg(self.figureIntensity)
        self.toolbarIntensity = NavigationToolbar2QT(self.canvasIntensity, self)
        self.intensityFigureVerticalLayout.addWidget(self.toolbarIntensity)
        self.intensityFigureVerticalLayout.addWidget(self.canvasIntensity, 1.0)
        self.axesIntensity = self.figureIntensity.add_subplot(1, 1, 1)
        self.figurePosition = Figure(constrained_layout=True)
        self.canvasPosition = FigureCanvasQTAgg(self.figurePosition)
        self.toolbarPosition = NavigationToolbar2QT(self.canvasPosition, self)
        self.positionFigureVerticalLayout.addWidget(self.toolbarPosition)
        self.positionFigureVerticalLayout.addWidget(self.canvasPosition, 1.0)
        gs = self.figurePosition.add_gridspec(4, 4)
        self.axesPosition = self.figurePosition.add_subplot(gs[1:, :-1])
        self.axesHPositionKDE = self.figurePosition.add_subplot(gs[0, :-1], sharex=self.axesPosition)
        self.axesVPositionKDE = self.figurePosition.add_subplot(gs[1:, -1], sharey=self.axesPosition)
        self.startStopToolButton.clicked.connect(self.startStop)
        self.clearBufferToolButton.clicked.connect(self.clearBuffer)
        self.shutterToolButton.toggled.connect(self.moveShutter)
        self.bufferLengthSpinBox.valueChanged.connect(self.resizeBuffer)
        self.debugModeGroupBox.setVisible(self.debugmode)
        self.resizeBuffer()

    def resizeBuffer(self):
        """Resize the measurement buffer"""

        # the measurement buffer is a 1-dimensional structured array, initially filled with NaNs. Measured data starts
        # being written from index 0, going towards the end. When the end is reached, the writing position loops back to
        # the start, overwriting previous points.
        newbuffer = np.empty(self.bufferLengthSpinBox.value(), dtype=self.bufferdtype)
        newbuffer[:] = np.nan
        if self.buffer is not None:
            # first rotate the old buffer
            if np.isnan(self.buffer['time']).sum():
                # there are still NaNs: we have not yet looped over. Next index to be written is `self.cursor`.
                oldbuffer = self.buffer[:self.cursor]
            else:
                # we have already looped over
                oldbuffer = np.hstack((self.buffer[self.cursor:], self.buffer[:self.cursor]))
            # see how much of the old buffer fits in the new one. Prefer the most recent elements
            newbuffer[:min(len(oldbuffer), len(newbuffer))] = oldbuffer[-min(len(oldbuffer), len(newbuffer)):]
        self.buffer = newbuffer
        self.cursor = (~np.isnan(self.buffer['time'])).sum() % len(self.buffer)
        self.redraw()

    def startStop(self):
        if self.startStopToolButton.text() == 'Start':
            # no measurement running, start it.
            self.startStopToolButton.setText('Stop')
            self.startStopToolButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/stop.svg')))
            if self.debugmode:
                self.startTimer(int(self.waitTimeDoubleSpinBox.value() * 1000), QtCore.Qt.PreciseTimer)
            else:
                self.instrument.exposer.exposureFinished.connect(self.onExposureFinished)
                self.instrument.exposer.imageReceived.connect(self.onImageReceived)
                self.instrument.exposer.startExposure('mon', self.expTimeDoubleSpinBox.value(), 1)
        else:
            # measurement is running, stop it
            self.startStopToolButton.setText('Start')
            self.startStopToolButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/start.svg')))
            if self.instrument.exposer.isExposing():
                self.instrument.exposer.stopExposure()

    def clearBuffer(self):
        self.buffer = np.empty(self.bufferLengthSpinBox.value(), dtype=self.bufferdtype)
        self.buffer[:] = np.nan
        self.cursor = 0
        self.redraw()

    def moveShutter(self, open: bool):
        source = self.instrument.devicemanager.source()
        assert isinstance(source, GeniX)
        source.moveShutter(open)

    def redraw(self):
        self.axesIntensity.clear()
        self.axesIntensity.set_xlabel('Time')
        self.axesIntensity.set_ylabel('Beam intensity')
        self.axesIntensity.grid(True, which='both')
        self.axesIntensity.plot(np.empty(len(self.buffer))+np.nan, np.empty(len(self.buffer))+np.nan, '.')
        self.axesPosition.clear()
        self.axesPosition.set_xlabel('Horizontal beam coordinate (pixel)')
        self.axesPosition.set_ylabel('Vertical beam coordinate (pixel)')
        self.axesPosition.grid(True, which='both')
#        validdata = np.isfinite(self.buffer['time'])
#        self.axesPosition.scatter(self.buffer['beamx'][validdata], self.buffer['beamy'][validdata],
#                                  c=self.buffer['time'][validdata], cmap='Blues')
        self.axesHPositionKDE.plot(np.empty(self.kdepointcount)+np.nan, np.empty(self.kdepointcount)+np.nan, '-')
        self.axesVPositionKDE.plot(np.empty(self.kdepointcount)+np.nan, np.empty(self.kdepointcount)+np.nan, '-')
        self.axesHPositionKDE.xaxis.set_ticks_position('top')
        self.axesHPositionKDE.xaxis.set_label_position('top')
        self.axesVPositionKDE.yaxis.set_ticks_position('right')
        self.axesVPositionKDE.yaxis.set_label_position('right')
        self.axesHPositionKDE.grid(True, which='both')
        self.axesVPositionKDE.grid(True, which='both')
        self.axesHPositionKDE.set_ylabel('KDE')
        self.axesVPositionKDE.set_xlabel('KDE')
        self.axesHPositionKDE.set_xlabel(self.axesPosition.get_xlabel())
        self.axesVPositionKDE.set_ylabel(self.axesPosition.get_ylabel())
        self.updateGraph()

    def timerEvent(self, event: QtCore.QTimerEvent):
        if self.debugmode:
            if self.startStopToolButton.text() == 'Start':
                self.killTimer(event.timerId())
            self.addPoint(
                np.random.default_rng().normal(
                    self.debugIntensityMeanDoubleSpinBox.value(),
                    self.debugIntensitySTDDoubleSpinBox.value(), 1),
                np.random.default_rng().normal(
                    self.debugBeamXMeanDoubleSpinBox.value(),
                    self.debugBeamXSTDDoubleSpinBox.value(), 1),
                np.random.default_rng().normal(
                    self.debugBeamYMeanDoubleSpinBox.value(),
                    self.debugBeamYSTDDoubleSpinBox.value(), 1)
            )
            self.cursor = (self.cursor + 1) % len(self.buffer)
            self.updateGraph()
        else:
            self.killTimer(event.timerId())
            self.instrument.exposer.startExposure('mon', self.expTimeDoubleSpinBox.value(), 1)


    def addPoint(self, intensity: float, x: float, y: float):
        self.buffer[self.cursor] = (time.thread_time(), intensity, x, y)
        self.cursor = (self.cursor + 1) % len(self.buffer)
        self.updateGraph()

    def updateGraph(self):
        try:
            self.axesPosition.collections[0].remove()
        except IndexError:
            pass
        validdata = np.isfinite(self.buffer['time'])
        beamx = self.buffer['beamx'][validdata]
        beamy = self.buffer['beamy'][validdata]
        timestamp = self.buffer['time'][validdata]
        intensity = self.buffer['intensity'][validdata]
        self.axesPosition.scatter(beamx, beamy, c=timestamp, cmap='Blues')
        self.axesIntensity.lines[0].set_xdata(self.buffer['time'])
        self.axesIntensity.lines[0].set_ydata(self.buffer['intensity'])
        self.axesPosition.relim()
        self.axesIntensity.relim()
        self.axesIntensity.autoscale_view()
        self.axesPosition.autoscale_view()
        if validdata.sum() >= 2:
            timeweight = np.exp(-(timestamp.max()-timestamp)/(timestamp.ptp()*0.1))
        else:
            timeweight=np.ones_like(timestamp)
        if validdata.sum() >= 2:
            kdex = np.linspace(self.buffer['beamx'][validdata].min(), self.buffer['beamx'][validdata].max(), self.kdepointcount)
            kde = (np.exp(-(beamx[np.newaxis, :]-kdex[:, np.newaxis])**2/(2*self.positionKDEWidthDoubleSpinBox.value()**2))*timeweight[np.newaxis,:]).sum(axis=1)
            self.axesHPositionKDE.lines[0].set_xdata(kdex)
            self.axesHPositionKDE.lines[0].set_ydata(kde)
            self.axesHPositionKDE.relim()
            self.axesHPositionKDE.autoscale_view()
            kdey = np.linspace(self.buffer['beamy'][validdata].min(), self.buffer['beamy'][validdata].max(), self.kdepointcount)
            kde = (np.exp(-(beamy[np.newaxis, :]-kdey[:, np.newaxis])**2/(2*self.positionKDEWidthDoubleSpinBox.value()**2))*timeweight[np.newaxis, :]).sum(axis=1)
            self.axesVPositionKDE.lines[0].set_xdata(kde)
            self.axesVPositionKDE.lines[0].set_ydata(kdey)
            self.axesVPositionKDE.relim()
            self.axesVPositionKDE.autoscale_view()

        self.canvasIntensity.draw_idle()
        self.canvasPosition.draw_idle()
        for label, dataset in [(self.intensityAverageLabel, intensity), (self.beamXAverageLabel, beamx), (self.beamYAverageLabel, beamy)]:
            mean = np.sum(dataset*timeweight)/np.sum(timeweight)
            sigma = (np.sum(dataset**2*timeweight)/np.sum(timeweight) - mean**2)**0.5
            label.setText(f'{mean:.2f} (σ={sigma:.2f})')

    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        assert isinstance(self.sender(), DeviceFrontend)
        if (self.sender().devicetype == 'source') and (name == 'shutter'):
            self.shutterToolButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/beamshutter_open.svg' if newvalue else ':/icons/beamshutter_closed.svg')))
            self.shutterToolButton.setText("Close shutter" if newvalue else "Open shutter")
            self.shutterToolButton.blockSignals(True)
            self.shutterToolButton.setChecked(newvalue)
            self.shutterToolButton.blockSignals(False)

    def onImageReceived(self, exposure: Exposure):
        sumimage, maximage, meanrow, meancol, stdrow, stdcol, pixelcount = beamweights(
            exposure.intensity, exposure.mask)
        self.addPoint(sumimage, meancol, meanrow)

    def onExposureFinished(self, success: bool):
        if (self.startStopToolButton.text() == 'Stop') and success:
            # measurement is still running, do another exposure
            self.startTimer(int(self.waitTimeDoubleSpinBox.value()*1000), QtCore.Qt.PreciseTimer)
        else:
            self.instrument.exposer.exposureFinished.disconnect(self.onExposureFinished)
            self.instrument.exposer.imageReceived.disconnect(self.onImageReceived)

