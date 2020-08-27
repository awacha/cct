import logging
from typing import Optional, Tuple

from PyQt5 import QtWidgets
from matplotlib.backend_bases import PickEvent
from matplotlib.widgets import Cursor

from .calibration_ui import Ui_MainWindow
from ...utils.fsnselector import FSNSelector
from ...utils.plotcurve import PlotCurve
from ...utils.plotimage import PlotImage
from ...utils.window import WindowRequiresDevices
from ....core2.algorithms.centering import findbeam, centeringalgorithms
from ....core2.dataclasses import Exposure, Curve

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Calibration(QtWidgets.QMainWindow, WindowRequiresDevices, Ui_MainWindow):
    fsnSelector: FSNSelector
    plotimage: PlotImage
    plotcurve: PlotCurve
    exposure: Optional[Exposure] = None
    curve: Optional[Curve] = None
    manualcursor: Optional[Cursor] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.fsnSelector = FSNSelector(self.fsnSelectorGroupBox)
        self.fsnSelectorGroupBox.setLayout(QtWidgets.QVBoxLayout())
        self.fsnSelectorGroupBox.layout().addWidget(self.fsnSelector)
        self.fsnSelector.fsnSelected.connect(self.onFSNSelected)
        self.tab2D.setLayout(QtWidgets.QVBoxLayout())
        self.plotimage = PlotImage(self.tab2D)
        self.tab2D.layout().addWidget(self.plotimage)
        self.tab1D.setLayout(QtWidgets.QVBoxLayout())
        self.plotcurve = PlotCurve(self.tab1D)
        self.tab1D.layout().addWidget(self.plotcurve)
        self.centeringMethodComboBox.addItems(sorted(centeringalgorithms))
        self.centeringMethodComboBox.setCurrentIndex(0)
        self.centeringPushButton.clicked.connect(self.findCenter)
        self.manualCenteringPushButton.clicked.connect(self.manualCentering)
        self.plotimage.canvas.mpl_connect('pick_event', self.on2DPick)
        self.plotimage.axes.set_picker(True)

    def on2DPick(self, event: PickEvent):
        if self.manualcursor is not None:
            if (event.mouseevent.button == 1):
                beamcol, beamrow = event.mouseevent.xdata, event.mouseevent.ydata
                self.updateBeamPosition((beamrow, 0), (beamcol, 0))
            self.manualcursor.set_active(False)
            self.manualcursor = None

    def onFSNSelected(self, prefix: str, index: int):
        logger.debug(f'FSN selected: {prefix=} {index=}')
        self.setExposure(self.instrument.io.loadExposure(prefix, index, raw=True, check_local=True))

    def setExposure(self, exposure: Exposure):
        self.exposure = exposure
        self.plotimage.setExposure(self.exposure)
        self.plotcurve.clear()
        self.curve = self.exposure.radial_average()
        self.plotcurve.addCurve(self.curve)
        self.plotcurve.setPixelMode(True)
        self.beamXDoubleSpinBox.setValue(self.exposure.header.beamposcol[0])
        self.beamXErrDoubleSpinBox.setValue(self.exposure.header.beamposcol[1])
        self.beamYDoubleSpinBox.setValue(self.exposure.header.beamposrow[0])
        self.beamYErrDoubleSpinBox.setValue(self.exposure.header.beamposrow[1])
        self.saveBeamXToolButton.setEnabled(False)
        self.saveBeamYToolButton.setEnabled(False)

    def findCenter(self):
        xmin, xmax, ymin, ymax = self.plotcurve.getRange()
        logger.debug(f'Range: {xmin=}, {xmax=}, {ymin=}, {ymax=}')
        if self.curve is None:
            return
        curve = self.curve.trim(xmin, xmax, ymin, ymax, bypixel=True)
        logger.debug(f'Trimmed curve has {len(curve)} points')
        rmin = curve.pixel.min()
        rmax = curve.pixel.max()
        logger.debug(f'{rmin=}, {rmax=}')
        algorithm = centeringalgorithms[self.centeringMethodComboBox.currentText()]
        self.updateBeamPosition(*findbeam(algorithm, self.exposure, rmin, rmax, 0, 0))

    def updateBeamPosition(self, row: Tuple[float, float], col: Tuple[float, float]):
        self.exposure.header.beamposrow = row
        self.exposure.header.beamposcol = col
        self.setExposure(self.exposure)
        self.saveBeamXToolButton.setEnabled(True)
        self.saveBeamYToolButton.setEnabled(True)


    def manualCentering(self):
        if self.manualcursor is not None:
            return
        self.manualcursor=Cursor(self.plotimage.axes, horizOn=True, vertOn=True, useblit=False, color='red', lw='1')
