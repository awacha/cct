import logging
from typing import Optional

from PyQt5 import QtWidgets
from sastool.classes2 import Exposure

from .calibration_ui import Ui_MainWindow
from ...utils.fsnselector import FSNSelector
from ...utils.plotcurve import PlotCurve
from ...utils.plotimage import PlotImage
from ...utils.window import WindowRequiresDevices

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Calibration(QtWidgets.QMainWindow, WindowRequiresDevices, Ui_MainWindow):
    fsnSelector: FSNSelector
    plotimage: PlotImage
    plotcurve: PlotCurve
    exposure: Optional[Exposure] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        self.fsnSelector = FSNSelector(self.fsnselectorPage)
        self.fsnSelector.fsnSelected.connect(self.onFSNSelected)
        self.tab2D.setLayout(QtWidgets.QVBoxLayout())
        self.plotimage = PlotImage(self.tab2D)
        self.tab2D.layout().addWidget(self.plotimage)
        self.tab1D.setLayout(QtWidgets.QVBoxLayout())
        self.plotcurve = PlotCurve(self.tab1D)
        self.tab1D.layout().addWidget(self.plotcurve)

    def onFSNSelected(self, prefix: str, index: int):
        logger.debug(f'FSN selected: {prefix=} {index=}')
        exposure = self.instrument.io.loadExposure(prefix, index, raw=True, check_local=True)
        self.plotimage.setExposure(exposure)
        self.plotcurve.clear()
        self.plotcurve.addCurve(exposure.radial_average())
        self.plotcurve.replot()
