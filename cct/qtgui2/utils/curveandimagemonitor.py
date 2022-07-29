from typing import Final, Union

from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import pyqtSlot as Slot

from .curveandimagemonitor_ui import Ui_Form
from .fsnselector import FSNSelector
from .plotcurve import PlotCurve
from .plotimage import PlotImage
from ..utils.window import WindowRequiresDevices


class ImageAndCurveMonitor(QtWidgets.QWidget, WindowRequiresDevices, Ui_Form):
    fsnselector: FSNSelector
    plotwidget: Union[PlotImage, PlotCurve]
    mode_image: bool

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setupUi(self)

    def setupUi(self, Form):
        super().setupUi(Form)
        self.fsnselector = FSNSelector(self)
        self.fsnSelectorHorizontalLayout.insertWidget(0, self.fsnselector, 1)
        self.plotwidget = PlotImage(self) if self.mode_image else PlotCurve(self)
        self.plotImageVerticalLayout.addWidget(self.plotwidget, 1)
        self.setWindowTitle('Image monitor' if self.mode_image else 'Curve monitor')
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icons/imagemonitor.svg" if self.mode_image else ':/icons/curvemonitor.svg'),
                       QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)
        self.fsnselector.fsnSelected.connect(self.onFSNSelected)
        self.instrument.io.lastFSNChanged.connect(self.onLastFSNChanged)
        self.autoUpdatePushButton.setChecked(True)

    @Slot(str, int)
    def onFSNSelected(self, prefix: str, fsn: int):
        ex = self.fsnselector.loadExposure()
        if isinstance(self.plotwidget, PlotCurve):
            self.plotwidget.clear()
            self.plotwidget.addCurve(
                ex.radial_average(),
                label=f'{prefix}/{ex.header.fsn}: {ex.header.title} @ {ex.header.distance[0]:.2f} mm')
            self.plotwidget.replot()
        elif isinstance(self.plotwidget, PlotImage):
            self.plotwidget.setExposure(
                ex, None,
                f'{prefix}/{ex.header.fsn}: {ex.header.title} @ {ex.header.distance[0]:.2f} mm')

    @Slot(str, int)
    def onLastFSNChanged(self, prefix: str, fsn: int):
        if (prefix == self.fsnselector.prefix()) and self.autoUpdatePushButton.isChecked():
            self.fsnselector.gotoLast()


class ImageMonitor(ImageAndCurveMonitor):
    mode_image: Final[bool] = True


class CurveMonitor(ImageAndCurveMonitor):
    mode_image: Final[bool] = False
