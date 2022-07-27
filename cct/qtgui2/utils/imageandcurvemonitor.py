from typing import Final

from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSlot as Slot

from .curveandimagemonitor_ui import Ui_Form
from ..utils.window import WindowRequiresDevices
from .fsnselector import FSNSelector
from .plotcurve import PlotCurve
from .plotimage import PlotImage


class ImageAndCurveMonitor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    fsnselector: FSNSelector
    plotimage: PlotImage
    plotcurve: PlotCurve
    mode_image: bool

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.fsnselector = FSNSelector(self)
        self.fsnSelectorHorizontalLayout.insertWidget(0, self.fsnselector, 1)
        if self.mode_image:
            self.plotimage = PlotImage(self)
            self.plotImageVerticalLayout.addWidget(self.plotimage, 1)
        else:
            self.plotcurve = PlotCurve(self)
            self.plotImageVerticalLayout.addWidget(self.plotcurve, 1)
        self.fsnselector.fsnSelected.connect(self.onFSNSelected)
        self.instrument.io.lastFSNChanged.connect(self.onLastFSNChanged)

    @Slot(str, int)
    def onFSNSelected(self, prefix: str, fsn: int):
        ex = self.fsnselector.loadExposure()
        if hasattr(self, 'plotcurve'):
            self.plotcurve.clear()
            self.plotcurve.addCurve(ex.radial_average())
            self.plotcurve.replot()
        if hasattr(self, 'plotimage'):
            self.plotimage.setExposure(ex, None,
                                       f'{prefix}/{ex.header.fsn}: {ex.header.title} @ {ex.header.distance[0]:.2f} mm')

    @Slot(str, int)
    def onLastFSNChanged(self, prefix: str, fsn: int):
        if prefix == self.fsnselector.prefix():
            self.fsnselector.gotoLast()


class ImageMonitor(ImageAndCurveMonitor):
    mode_image: Final[bool] = True


class CurveMonitor(ImageAndCurveMonitor):
    mode_image: Final[bool] = False
