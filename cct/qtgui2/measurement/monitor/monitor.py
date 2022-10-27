import logging
import time
from typing import Optional, Final, Any

import numpy as np
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import pyqtSlot as Slot
from matplotlib.axes import Axes
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT, FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import matplotlib.transforms

from .monitor_ui import Ui_Form
from ...utils.window import WindowRequiresDevices
from ...utils.plotimage import PlotImage
from ....core2.devices.xraysource import GeniX
from ....core2.devices import DeviceFrontend, DeviceType
from ....core2.dataclasses import Exposure
from ....core2.algorithms.beamweighting import beamweights

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MonitorMeasurement(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    required_devicetypes = [DeviceType.Source, DeviceType.Detector]
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
    xTargetLine: Optional[Line2D] = None
    yTargetLine: Optional[Line2D] = None
    xTargetLineKDE: Optional[Line2D] = None
    yTargetLineKDE: Optional[Line2D] = None
    intensityTargetLine: Optional[Line2D] = None
    buffer: Optional[np.ndarray] = None
    cursor: Optional[int] = None  # point in the buffer where the next measurement will be written
    bufferdtype: Final[np.dtype] = np.dtype([('time', 'f4'), ('intensity', 'f4'), ('beamx', 'f4'), ('beamy', 'f4'), ])
    kdepointcount: Final[int] = 1000
    debugmode: bool=False
    plotimage: PlotImage

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.plotimage = PlotImage(self)
        self.plotImageVerticalLayout.addWidget(self.plotimage, 1)
        self.plotimage.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.MinimumExpanding)
        self.figureIntensity = Figure(constrained_layout=True)
        self.canvasIntensity = FigureCanvasQTAgg(self.figureIntensity)
        self.toolbarIntensity = NavigationToolbar2QT(self.canvasIntensity, self)
        self.intensityFigureVerticalLayout.addWidget(self.toolbarIntensity)
        self.intensityFigureVerticalLayout.addWidget(self.canvasIntensity)
        self.axesIntensity = self.figureIntensity.add_subplot(1, 1, 1)
        self.figurePosition = Figure(constrained_layout=True)
        self.canvasPosition = FigureCanvasQTAgg(self.figurePosition)
        self.toolbarPosition = NavigationToolbar2QT(self.canvasPosition, self)
        self.positionFigureVerticalLayout.addWidget(self.toolbarPosition)
        self.positionFigureVerticalLayout.addWidget(self.canvasPosition)
        gs = self.figurePosition.add_gridspec(4, 4)
        self.axesPosition = self.figurePosition.add_subplot(gs[1:, :-1])
        self.axesHPositionKDE = self.figurePosition.add_subplot(gs[0, :-1], sharex=self.axesPosition)
        self.axesVPositionKDE = self.figurePosition.add_subplot(gs[1:, -1], sharey=self.axesPosition)
        self.startStopToolButton.clicked.connect(self.startStop)
        self.clearBufferToolButton.clicked.connect(self.clearBuffer)
        self.shutterToolButton.toggled.connect(self.moveShutter)
        self.bufferLengthSpinBox.valueChanged.connect(self.resizeBuffer)
        self.debugModeGroupBox.setVisible(self.debugmode)
        self.beamXTargetCheckBox.toggled.connect(self.updateTargetLines)
        self.beamYTargetCheckBox.toggled.connect(self.updateTargetLines)
        self.intensityTargetCheckBox.toggled.connect(self.updateTargetLines)
        self.beamXTargetDoubleSpinBox.valueChanged.connect(self.updateTargetLines)
        self.beamYTargetDoubleSpinBox.valueChanged.connect(self.updateTargetLines)
        self.intensityTargetDoubleSpinBox.valueChanged.connect(self.updateTargetLines)
        self.resizeBuffer()

    @Slot()
    def updateTargetLines(self):
        logger.debug(f'UpdateTargetLines() called from {self.sender().objectName()=}')
        if self.xTargetLine is not None:
            logger.debug('xTargetLine')
            self.xTargetLine.set_xdata(self.beamXTargetDoubleSpinBox.value())
            self.xTargetLine.set_visible(self.beamXTargetCheckBox.isChecked())
        if self.yTargetLine is not None:
            logger.debug('yTargetLine')
            self.yTargetLine.set_ydata(self.beamYTargetDoubleSpinBox.value())
            self.yTargetLine.set_visible(self.beamYTargetCheckBox.isChecked())
        if self.xTargetLineKDE is not None:
            logger.debug('xTargetLineKDE')
            self.xTargetLineKDE.set_xdata(self.beamXTargetDoubleSpinBox.value())
            self.xTargetLineKDE.set_visible(self.beamXTargetCheckBox.isChecked())
        if self.yTargetLineKDE is not None:
            logger.debug('yTargetLineKDE')
            self.yTargetLineKDE.set_ydata(self.beamYTargetDoubleSpinBox.value())
            self.yTargetLineKDE.set_visible(self.beamYTargetCheckBox.isChecked())
        if self.intensityTargetLine is not None:
            logger.debug('intensityTargetLine')
            self.intensityTargetLine.set_ydata(self.intensityTargetDoubleSpinBox.value())
            self.intensityTargetLine.set_visible(self.intensityTargetCheckBox.isChecked())
#        return
        self.axesPosition.relim(visible_only=True)
        self.axesPosition.autoscale_view(False)
        self.axesHPositionKDE.relim(visible_only=True)
        self.axesHPositionKDE.autoscale_view(False)
        self.axesVPositionKDE.relim(visible_only=True)
        self.axesVPositionKDE.autoscale_view(False)
        self.axesIntensity.relim(visible_only=True)
        self.axesIntensity.autoscale_view(False)
        self.canvasPosition.draw_idle()
        self.canvasIntensity.draw_idle()

    @Slot()
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

    @Slot()
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

    @Slot()
    def clearBuffer(self):
        self.buffer = np.empty(self.bufferLengthSpinBox.value(), dtype=self.bufferdtype)
        self.buffer[:] = np.nan
        self.cursor = 0
        self.redraw()

    @Slot()
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
        self.intensityTargetLine = self.axesIntensity.axhline(self.intensityTargetDoubleSpinBox.value(), color='red')
        self.intensityTargetLine.set_visible(self.intensityTargetCheckBox.isChecked())
        self.axesPosition.clear()
        self.axesPosition.set_xlabel('Horizontal beam coordinate (pixel)')
        self.axesPosition.set_ylabel('Vertical beam coordinate (pixel)')
        self.axesPosition.grid(True, which='both')
        self.xTargetLine = self.axesPosition.axvline(self.beamXTargetDoubleSpinBox.value(), color='red')
        self.xTargetLine.set_visible(self.beamXTargetCheckBox.isChecked())
        self.yTargetLine = self.axesPosition.axhline(self.beamYTargetDoubleSpinBox.value(), color='red')
        self.yTargetLine.set_visible(self.beamYTargetCheckBox.isChecked())
#        validdata = np.isfinite(self.buffer['time'])
#        self.axesPosition.scatter(self.buffer['beamx'][validdata], self.buffer['beamy'][validdata],
#                                  c=self.buffer['time'][validdata], cmap='Blues')
        self.axesHPositionKDE.plot(np.empty(self.kdepointcount)+np.nan, np.empty(self.kdepointcount)+np.nan, '-')
        self.axesVPositionKDE.plot(np.empty(self.kdepointcount)+np.nan, np.empty(self.kdepointcount)+np.nan, '-')
        self.xTargetLineKDE = self.axesHPositionKDE.axvline(self.beamXTargetDoubleSpinBox.value(), color='red')
        self.xTargetLineKDE.set_visible(self.beamXTargetCheckBox.isChecked())
        self.yTargetLineKDE = self.axesVPositionKDE.axhline(self.beamYTargetDoubleSpinBox.value(), color='red')
        self.yTargetLineKDE.set_visible(self.beamYTargetCheckBox.isChecked())
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
        validdata = np.logical_and(
            np.logical_and(
                np.isfinite(self.buffer['time']),
                np.isfinite(self.buffer['intensity'])
            ),
            np.logical_and(
                np.isfinite(self.buffer['beamx']),
                np.isfinite(self.buffer['beamy'])
            ))
        beamx = self.buffer['beamx'][validdata]
        beamy = self.buffer['beamy'][validdata]
        timestamp = self.buffer['time'][validdata]
        intensity = self.buffer['intensity'][validdata]
        self.axesPosition.scatter(beamx, beamy, c=timestamp, cmap='Blues')
        self.axesIntensity.lines[0].set_xdata(self.buffer['time'])
        self.axesIntensity.lines[0].set_ydata(self.buffer['intensity'])
        if validdata.sum() > 0:
            self.axesPosition.dataLim = matplotlib.transforms.Bbox.unit()
            self.axesPosition.dataLim.update_from_data_xy(np.vstack((self.buffer['beamx'], self.buffer['beamy'])).T[validdata,:], ignore=True)
            xmargin, ymargin = self.axesPosition.margins()
            width= self.axesPosition.dataLim.width
            height = self.axesPosition.dataLim.height
            self.axesPosition.set_xlim(self.axesPosition.dataLim.xmin - width*xmargin, self.axesPosition.dataLim.xmax+width*xmargin)
            self.axesPosition.set_ylim(self.axesPosition.dataLim.ymin - height*ymargin, self.axesPosition.dataLim.ymax+height*ymargin)
            logger.debug(f'{self.axesPosition.dataLim=}')
        self.axesIntensity.relim(visible_only=True)
        self.axesIntensity.autoscale_view(False)
        if validdata.sum() >= 2:
            timeweight = np.exp(-(timestamp.max()-timestamp)/(timestamp.ptp()*0.1))
        else:
            timeweight=np.ones_like(timestamp)
        if validdata.sum() >= 2:
            kdex = np.linspace(self.buffer['beamx'][validdata].min(), self.buffer['beamx'][validdata].max(), self.kdepointcount)
            kde = (np.exp(-(beamx[np.newaxis, :]-kdex[:, np.newaxis])**2/(2*self.positionKDEWidthDoubleSpinBox.value()**2))*timeweight[np.newaxis,:]).sum(axis=1)
            self.axesHPositionKDE.lines[0].set_xdata(kdex)
            self.axesHPositionKDE.lines[0].set_ydata(kde)
            self.axesHPositionKDE.set_ylim(kde.min()-kde.ptp()*0.1, kde.max()+kde.ptp()*0.1)

            kdey = np.linspace(self.buffer['beamy'][validdata].min(), self.buffer['beamy'][validdata].max(), self.kdepointcount)
            kde = (np.exp(-(beamy[np.newaxis, :]-kdey[:, np.newaxis])**2/(2*self.positionKDEWidthDoubleSpinBox.value()**2))*timeweight[np.newaxis, :]).sum(axis=1)
            self.axesVPositionKDE.lines[0].set_xdata(kde)
            self.axesVPositionKDE.lines[0].set_ydata(kdey)
            self.axesVPositionKDE.set_xlim(kde.min()-kde.ptp()*0.1, kde.max()+kde.ptp()*0.1)
#            self.axesVPositionKDE.relim(visible_only=True)
#            self.axesVPositionKDE.autoscale_view(vis)

        self.canvasIntensity.draw_idle()
        self.canvasPosition.draw_idle()
        for label, dataset in [(self.intensityAverageLabel, intensity), (self.beamXAverageLabel, beamx), (self.beamYAverageLabel, beamy)]:
            validpoints = np.isfinite(dataset)
            mean = np.sum(dataset[validpoints]*timeweight[validpoints])/np.sum(timeweight[validpoints])
            sigma = (np.sum(dataset[validpoints]**2*timeweight[validpoints])/np.sum(timeweight[validpoints]) - mean**2)**0.5
            label.setText(f'{mean:.2f} (σ={sigma:.2f})')

    @Slot(str, object, object)
    def onVariableChanged(self, name: str, newvalue: Any, prevvalue: Any):
        assert isinstance(self.sender(), DeviceFrontend)
        if (self.sender().devicetype == DeviceType.Source) and (name == 'shutter'):
            self.shutterToolButton.setIcon(QtGui.QIcon(QtGui.QPixmap(':/icons/beamshutter_open.svg' if newvalue else ':/icons/beamshutter_closed.svg')))
            self.shutterToolButton.setText("Close shutter" if newvalue else "Open shutter")
            self.shutterToolButton.blockSignals(True)
            self.shutterToolButton.setChecked(newvalue)
            self.shutterToolButton.blockSignals(False)

    @Slot(object)
    def onImageReceived(self, exposure: Exposure):
        sumimage, maximage, meanrow, meancol, stdrow, stdcol, pixelcount = beamweights(
            exposure.intensity, exposure.mask)
        logger.debug(f'{sumimage=}, {maximage=}, {meanrow=}, {meancol=}, {stdrow=}, {stdcol=}, {pixelcount=}')
        self.addPoint(sumimage, meancol, meanrow)
        self.plotimage.setExposure(exposure, keepzoom=None)

    @Slot(bool)
    def onExposureFinished(self, success: bool):
        if (self.startStopToolButton.text() == 'Stop') and success:
            # measurement is still running, do another exposure
            self.startTimer(int(self.waitTimeDoubleSpinBox.value()*1000), QtCore.Qt.PreciseTimer)
        else:
            self.instrument.exposer.exposureFinished.disconnect(self.onExposureFinished)
            self.instrument.exposer.imageReceived.disconnect(self.onImageReceived)

